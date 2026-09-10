"""A small, broker-less, staged message bus.

The bus decomposes work into *stages* (``Channel`` instances). Each stage has

* a bounded queue (admission control),
* a back-pressure policy for when that queue is full (load conditioning),
* a concurrency limit (how many envelopes the stage may process at once), and
* one or more consumers.

A single shared worker pool drains every stage. Producers are decoupled from
consumers by the queues, and no stage can monopolise the pool because each is
capped by its own concurrency limit.

What this is not: SEDA's original design also included a controller that
watched per-stage latency and queue depth at runtime and re-tuned thread
allocation and shed load automatically. That adaptive controller is future
work (see the README). This is the static-configuration core it builds on.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Callable, Protocol, runtime_checkable

from .envelope import Envelope, target_service

log = logging.getLogger("seda_bus")

# Number of envelopes a single drain task processes before releasing its
# concurrency permit and rescheduling. Amortises scheduling overhead without
# letting one task starve the others.
_BATCH = 16


class Delivery(Enum):
    POINT_TO_POINT = "p2p"  # one consumer handles each envelope (round robin)
    PUB_SUB = "pubsub"      # every consumer handles every envelope


class Backpressure(Enum):
    BLOCK = "block"              # producer waits (up to timeout) for room
    REJECT = "reject"            # publish() returns False immediately
    DROP_NEWEST = "drop_newest"  # silently discard the envelope being offered
    DROP_OLDEST = "drop_oldest"  # evict the head of the queue to make room


@runtime_checkable
class Consumer(Protocol):
    def receive(self, envelope: Envelope) -> bool:  # pragma: no cover - protocol
        """Handle an envelope. Return True to ack, False to nack (retry)."""


ConsumerLike = Consumer | Callable[[Envelope], bool]


def _as_consumer(c: ConsumerLike) -> Consumer:
    if isinstance(c, Consumer):
        return c
    if callable(c):
        class _Fn:
            def receive(self, envelope: Envelope) -> bool:
                return bool(c(envelope))
        return _Fn()
    raise TypeError(f"{c!r} is neither a Consumer nor callable")


class ChannelStats:
    __slots__ = ("enqueued", "delivered", "nacked", "dropped", "dead_lettered")

    def __init__(self) -> None:
        self.enqueued = 0
        self.delivered = 0
        self.nacked = 0
        self.dropped = 0
        self.dead_lettered = 0

    def snapshot(self, depth: int) -> dict[str, int]:
        return {
            "depth": depth,
            "enqueued": self.enqueued,
            "delivered": self.delivered,
            "nacked": self.nacked,
            "dropped": self.dropped,
            "dead_lettered": self.dead_lettered,
        }


class Channel:
    """One stage: a bounded queue plus its consumers."""

    def __init__(
        self,
        name: str,
        *,
        capacity: int = 1024,
        concurrency: int = 1,
        delivery: Delivery = Delivery.POINT_TO_POINT,
        backpressure: Backpressure = Backpressure.BLOCK,
        max_attempts: int = 1,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        self.name = name
        self.capacity = capacity
        self.delivery = delivery
        self.backpressure = backpressure
        self.max_attempts = max_attempts

        self._q: deque[Envelope] = deque()
        self._lock = threading.Lock()
        self._not_full = threading.Condition(self._lock)
        self._permits = threading.BoundedSemaphore(concurrency)
        self._consumers: list[Consumer] = []
        self._rr = 0
        #: per-hop delivery attempts, keyed by envelope id (mirrors
        #: ``SEDAMessageChannel.attempts`` in seda-bus-java).
        self._attempts: dict[str, int] = {}
        self.stats = ChannelStats()

    def bump_attempt(self, env_id: str) -> int:
        with self._lock:
            n = self._attempts.get(env_id, 0) + 1
            self._attempts[env_id] = n
            return n

    def clear_attempt(self, env_id: str) -> None:
        with self._lock:
            self._attempts.pop(env_id, None)

    # -- consumer registration -------------------------------------------------
    def subscribe(self, consumer: ConsumerLike) -> None:
        with self._lock:
            self._consumers.append(_as_consumer(consumer))

    def consumers(self) -> list[Consumer]:
        with self._lock:
            return list(self._consumers)

    # -- queue ---------------------------------------------------------------
    def depth(self) -> int:
        with self._lock:
            return len(self._q)

    def offer(self, env: Envelope, timeout: float | None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._not_full:
            while len(self._q) >= self.capacity:
                if self.backpressure is Backpressure.REJECT:
                    self.stats.dropped += 1
                    return False
                if self.backpressure is Backpressure.DROP_NEWEST:
                    self.stats.dropped += 1
                    return False
                if self.backpressure is Backpressure.DROP_OLDEST:
                    self._q.popleft()
                    self.stats.dropped += 1
                    break
                # BLOCK
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    self.stats.dropped += 1
                    return False
                self._not_full.wait(remaining)
            self._q.append(env)
            self.stats.enqueued += 1
            return True

    def poll(self) -> Envelope | None:
        with self._not_full:
            if not self._q:
                return None
            env = self._q.popleft()
            self._not_full.notify()
            return env

    def requeue(self, env: Envelope) -> None:
        """Put a nacked envelope back at the head for another attempt."""
        with self._not_full:
            self._q.appendleft(env)

    # -- concurrency permits ------------------------------------------------
    def try_acquire(self) -> bool:
        return self._permits.acquire(blocking=False)

    def release(self) -> None:
        try:
            self._permits.release()
        except ValueError:  # pragma: no cover - defensive
            pass


class SEDABus:
    """The bus: registry of channels + one shared worker pool."""

    def __init__(self, *, workers: int | None = None) -> None:
        self._workers = workers or os.cpu_count() or 4
        self._channels: dict[str, Channel] = {}
        self._dlq: dict[str, Channel] = {}
        self._callbacks: dict[str, Callable[[Envelope], None]] = {}
        self._reg_lock = threading.RLock()
        self._cb_lock = threading.Lock()
        self._pool: ThreadPoolExecutor | None = None
        self._running = threading.Event()
        self._accepting = threading.Event()

    # -- lifecycle --------------------------------------------------------
    def start(self) -> None:
        if self._running.is_set():
            return
        self._pool = ThreadPoolExecutor(
            max_workers=self._workers, thread_name_prefix="seda"
        )
        self._running.set()
        self._accepting.set()
        log.info("SEDABus started with %d workers", self._workers)

    def pause(self) -> None:
        self._accepting.clear()

    def resume(self) -> None:
        if self._running.is_set():
            self._accepting.set()

    def shutdown(self, timeout: float = 30.0) -> bool:
        """Stop accepting, drain what is queued (up to ``timeout``), then stop."""
        self._accepting.clear()
        drained = self._await_drain(timeout)
        self._teardown(wait=True)
        return drained

    def shutdown_now(self) -> None:
        self._accepting.clear()
        self._teardown(wait=False)

    def _teardown(self, *, wait: bool) -> None:
        self._running.clear()
        if self._pool is not None:
            self._pool.shutdown(wait=wait, cancel_futures=not wait)
            self._pool = None

    def _await_drain(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all(c.depth() == 0 for c in self._channels.values()):
                return True
            time.sleep(0.01)
        return all(c.depth() == 0 for c in self._channels.values())

    # -- registration ---------------------------------------------------
    def channel(self, name: str, **opts) -> Channel:
        with self._reg_lock:
            if name in self._channels:
                return self._channels[name]
            ch = Channel(name, **opts)
            self._channels[name] = ch
            return ch

    def get_channel(self, name: str) -> Channel | None:
        return self._channels.get(name)

    def set_dead_letter_channel(self, source: str, dlq: str) -> None:
        """Route dead letters from ``source`` to channel ``dlq``."""
        with self._reg_lock:
            self._dlq[source] = self.channel(dlq)

    def subscribe(self, channel_name: str, consumer: ConsumerLike) -> None:
        self.channel(channel_name).subscribe(consumer)

    # -- publishing -----------------------------------------------------
    def publish(
        self,
        env: Envelope,
        *,
        timeout: float | None = None,
        on_complete: Callable[[Envelope], None] | None = None,
    ) -> bool:
        if not self._running.is_set() or not self._accepting.is_set():
            return False
        name = target_service(env)
        ch = self._channels.get(name) if name is not None else None
        if ch is None:
            log.warning("no channel %r; dropping envelope %s", name, env.id)
            return False
        if on_complete is not None:
            with self._cb_lock:
                self._callbacks[env.id] = on_complete
        if not ch.offer(env, timeout):
            with self._cb_lock:
                self._callbacks.pop(env.id, None)
            return False
        self._schedule(ch)
        return True

    # -- scheduling / draining ----------------------------------------
    def _schedule(self, ch: Channel) -> None:
        pool = self._pool
        if pool is None:
            return
        while ch.depth() > 0 and ch.try_acquire():
            try:
                pool.submit(self._drain, ch)
            except RuntimeError:  # pool shutting down
                ch.release()
                return

    def _drain(self, ch: Channel) -> None:
        try:
            for _ in range(_BATCH):
                if not self._running.is_set():
                    return
                env = ch.poll()
                if env is None:
                    return
                self._process(ch, env)
        finally:
            ch.release()
            if self._running.is_set():
                self._schedule(ch)

    def _process(self, ch: Channel, env: Envelope) -> None:
        consumers = ch.consumers()
        if not consumers:
            log.warning("channel %r has no consumers; dead-lettering %s",
                        ch.name, env.id)
            self._dead_letter(ch, env)
            return

        attempt = ch.bump_attempt(env.id)
        if ch.delivery is Delivery.PUB_SUB:
            ok = True
            for c in consumers:
                ok = self._safe_receive(c, env) and ok
        else:
            idx = ch._rr % len(consumers)
            ch._rr = (ch._rr + 1) % len(consumers)
            ok = self._safe_receive(consumers[idx], env)

        if ok:
            ch.stats.delivered += 1
            ch.clear_attempt(env.id)
            self._complete_hop(env)
        elif attempt < ch.max_attempts:
            ch.stats.nacked += 1
            ch.requeue(env)
        else:
            ch.stats.nacked += 1
            ch.clear_attempt(env.id)
            self._dead_letter(ch, env)

    @staticmethod
    def _safe_receive(c: Consumer, env: Envelope) -> bool:
        try:
            return bool(c.receive(env))
        except Exception:  # a misbehaving consumer must not kill the worker
            log.exception("consumer %r raised handling %s", c, env.id)
            return False

    def _complete_hop(self, env: Envelope) -> None:
        if env.dynamic_routing_slip.peek_at_next_route() is not None:
            env.ratchet()
            # Re-publish to the next stage. Block briefly so an in-flight
            # itinerary is not silently dropped by a full downstream queue.
            self.publish(env, timeout=5.0)
            return
        with self._cb_lock:
            cb = self._callbacks.pop(env.id, None)
        if cb is not None:
            try:
                cb(env)
            except Exception:  # pragma: no cover - defensive
                log.exception("on_complete callback raised for %s", env.id)

    def _dead_letter(self, ch: Channel, env: Envelope) -> None:
        ch.stats.dead_lettered += 1
        dlq = self._dlq.get(ch.name)
        if dlq is not None:
            dlq.offer(env, timeout=0)
            self._schedule(dlq)
        with self._cb_lock:
            self._callbacks.pop(env.id, None)

    # -- introspection ------------------------------------------------
    def stats(self) -> dict[str, dict[str, int]]:
        return {
            name: ch.stats.snapshot(ch.depth())
            for name, ch in self._channels.items()
        }

    def __enter__(self) -> "SEDABus":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()
