"""End-to-end correctness tests for the bus (GIL or free-threaded)."""

from __future__ import annotations

import threading
import time

import pytest

from seda_bus import Backpressure, Delivery, SEDABus, make_envelope


@pytest.fixture()
def bus():
    b = SEDABus(workers=4)
    b.start()
    try:
        yield b
    finally:
        b.shutdown(timeout=5)


def _wait(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.005)
    return pred()


def test_point_to_point_round_robins(bus):
    hits = {"a": 0, "b": 0}
    lock = threading.Lock()

    def mk(key):
        def recv(_env):
            with lock:
                hits[key] += 1
            return True
        return recv

    bus.channel("work", capacity=100)
    bus.subscribe("work", mk("a"))
    bus.subscribe("work", mk("b"))

    for i in range(20):
        assert bus.publish(make_envelope("work", i))

    assert _wait(lambda: hits["a"] + hits["b"] == 20)
    assert hits["a"] == 10 and hits["b"] == 10


def test_pub_sub_fans_out(bus):
    seen_a, seen_b = [], []
    bus.channel("events", capacity=100, delivery=Delivery.PUB_SUB)
    bus.subscribe("events", lambda e: seen_a.append(e.content()) is None)
    bus.subscribe("events", lambda e: seen_b.append(e.content()) is None)

    for i in range(5):
        bus.publish(make_envelope("events", i))

    assert _wait(lambda: len(seen_a) == 5 and len(seen_b) == 5)
    assert sorted(seen_a) == sorted(seen_b) == list(range(5))


def test_routing_slip_visits_every_stage_in_order(bus):
    trail: list[str] = []
    lock = threading.Lock()

    for name in ("one", "two", "three"):
        bus.channel(name, capacity=50)
        bus.subscribe(name, (lambda n: lambda e: (
            lock.acquire(), trail.append(n), lock.release(), True)[-1])(name))

    completed = threading.Event()
    bus.publish(
        make_envelope("one", "x", slip=["two", "three"]),
        on_complete=lambda _e: completed.set(),
    )

    assert completed.wait(5)
    assert trail == ["one", "two", "three"]


def test_backpressure_reject_when_full(bus):
    gate = threading.Event()
    bus.channel("slow", capacity=2, concurrency=1,
                backpressure=Backpressure.REJECT)
    bus.subscribe("slow", lambda e: (gate.wait(5), True)[-1])

    accepted = [bus.publish(make_envelope("slow", i)) for i in range(10)]
    gate.set()

    # 1 in-flight + 2 queued accepted; the rest rejected.
    assert sum(accepted) <= 3
    assert accepted.count(False) >= 7
    assert bus.stats()["slow"]["dropped"] >= 7


def test_nack_retries_then_dead_letters(bus):
    attempts = {"n": 0}
    lock = threading.Lock()

    bus.channel("flaky", capacity=10, max_attempts=3)
    bus.channel("dead", capacity=10)
    bus.set_dead_letter_channel("flaky", "dead")

    dead_seen = threading.Event()
    bus.subscribe("dead", lambda e: dead_seen.set() or True)

    def always_fail(_e):
        with lock:
            attempts["n"] += 1
        return False

    bus.subscribe("flaky", always_fail)
    bus.publish(make_envelope("flaky", "boom"))

    assert dead_seen.wait(5)
    assert attempts["n"] == 3
    assert bus.stats()["flaky"]["dead_lettered"] == 1


def test_shutdown_drains_queued_work(bus):
    done = {"n": 0}
    lock = threading.Lock()

    def slow(_e):
        time.sleep(0.02)
        with lock:
            done["n"] += 1
        return True

    bus.channel("drain", capacity=200, concurrency=4)
    bus.subscribe("drain", slow)
    for i in range(50):
        bus.publish(make_envelope("drain", i))

    assert bus.shutdown(timeout=10) is True
    assert done["n"] == 50


def test_publish_after_pause_is_rejected(bus):
    bus.channel("p", capacity=10)
    bus.subscribe("p", lambda e: True)
    bus.pause()
    assert bus.publish(make_envelope("p", 1)) is False
    bus.resume()
    assert bus.publish(make_envelope("p", 2)) is True


def test_unknown_channel_returns_false(bus):
    assert bus.publish(make_envelope("nope", 1)) is False


# -- Correctness suite (see ../../CORRECTNESS_SUITE.md) --------------------
#
# C1: backpressure policy correctness, all four policies. Reject is already
# covered above (test_backpressure_reject_when_full).


def test_backpressure_block_waits_for_room(bus):
    gate = threading.Event()
    ch = bus.channel("tight", capacity=2, concurrency=1,
                      backpressure=Backpressure.BLOCK)
    bus.subscribe("tight", lambda e: (gate.wait(5), True)[-1])

    total = 10
    accepted: list[bool] = []

    def producer():
        for i in range(total):
            accepted.append(bus.publish(make_envelope("tight", i)))

    t = threading.Thread(target=producer)
    t.start()
    # Wait until the queue is provably full (the producer is now genuinely
    # blocked, not just running ahead of a lucky race) before releasing the
    # gate - a bare sleep would let this test pass even if Block silently
    # degraded into something else.
    assert _wait(lambda: ch.depth() >= 2, timeout=2)
    gate.set()
    t.join(10)
    assert not t.is_alive(), (
        "producer thread never returned from a Block publish - lost wakeup or stuck"
    )
    assert len(accepted) == total
    assert all(accepted)


def test_backpressure_drop_newest_matches_reject(bus):
    # DropNewest and Reject are the same observable outcome from the
    # caller's side - "don't admit the new one" - matching every other
    # seda-bus port's identical treatment of the two. This test exists to
    # confirm the policy is actually wired through offer(), not silently
    # ignored (e.g. falling through to Block's default).
    gate = threading.Event()
    bus.channel("dn", capacity=2, concurrency=1,
                backpressure=Backpressure.DROP_NEWEST)
    bus.subscribe("dn", lambda e: (gate.wait(5), True)[-1])

    accepted = [bus.publish(make_envelope("dn", i)) for i in range(10)]
    gate.set()

    assert sum(accepted) <= 3
    assert accepted.count(False) >= 7
    assert bus.stats()["dn"]["dropped"] >= 7


def test_backpressure_drop_oldest_evicts_instead_of_rejecting(bus):
    gate = threading.Event()
    ch = bus.channel("bounded", capacity=2, concurrency=1,
                      backpressure=Backpressure.DROP_OLDEST)
    bus.subscribe("bounded", lambda e: (gate.wait(5), True)[-1])

    accepted = [bus.publish(make_envelope("bounded", i)) for i in range(10)]
    depth_at_full = ch.depth()
    gate.set()

    # DropOldest must never reject for capacity reasons - the newest
    # envelope is always admitted by evicting the oldest queued one.
    assert all(accepted)
    assert depth_at_full <= 2
    assert bus.stats()["bounded"]["dropped"] >= 1


# C2: retry -> dead-letter correctness. The "exhausts every attempt" path is
# already covered above (test_nack_retries_then_dead_letters).


def test_nack_retry_succeeds_on_final_attempt_and_clears_attempt_state(bus):
    attempts = {"n": 0}
    lock = threading.Lock()
    delivered = threading.Event()

    ch = bus.channel("flaky2", capacity=10, max_attempts=3)

    def fail_twice_then_succeed(_e):
        with lock:
            attempts["n"] += 1
            n = attempts["n"]
        if n < 3:
            return False
        delivered.set()
        return True

    bus.subscribe("flaky2", fail_twice_then_succeed)
    bus.publish(make_envelope("flaky2", "eventually-ok"))

    assert delivered.wait(5)
    assert attempts["n"] == 3
    assert bus.stats()["flaky2"]["delivered"] == 1
    assert bus.stats()["flaky2"]["dead_lettered"] == 0
    # A terminal outcome (success, same as dead-lettering) must clear the
    # per-envelope attempt-tracking entry - otherwise it leaks for the life
    # of the channel on any workload that ever retries.
    assert ch._attempts == {}


def test_channel_with_no_consumers_dead_letters_immediately(bus):
    dead_seen = threading.Event()
    bus.channel("orphan", capacity=10)
    bus.channel("orphan-dead", capacity=10)
    bus.set_dead_letter_channel("orphan", "orphan-dead")
    bus.subscribe("orphan-dead", lambda e: dead_seen.set() or True)

    bus.publish(make_envelope("orphan", "nobody-home"))

    assert dead_seen.wait(5)
    assert bus.stats()["orphan"]["dead_lettered"] == 1


# C3: a raising consumer must not take the bus down, and every other
# envelope - before and after the raise - must still be delivered.


def test_consumer_exception_isolation(bus):
    delivered: list[int] = []
    lock = threading.Lock()

    def raise_on_multiples_of_three(e):
        n = e.content()
        if n % 3 == 0:
            raise RuntimeError("boom")
        with lock:
            delivered.append(n)
        return True

    bus.channel("shaky", capacity=50, max_attempts=1)
    bus.subscribe("shaky", raise_on_multiples_of_three)

    for i in range(15):
        assert bus.publish(make_envelope("shaky", i))

    assert _wait(lambda: len(delivered) == 10, timeout=5)
    assert sorted(delivered) == [i for i in range(15) if i % 3 != 0]
    assert bus.stats()["shaky"]["dead_lettered"] == 5


# C4: shutdown(timeout) must never lose track of a published envelope -
# delivered + dead_lettered (+ whatever's still visibly queued, if the
# timeout expired first) must equal what was published.


def test_shutdown_accounting_matches_published_when_drained_in_time(bus):
    bus.channel("d1", capacity=200, concurrency=4)
    bus.subscribe("d1", lambda e: (time.sleep(0.01), True)[-1])
    for i in range(30):
        bus.publish(make_envelope("d1", i))

    drained = bus.shutdown(timeout=10)
    assert drained is True
    s = bus.stats()["d1"]
    assert s["delivered"] + s["dead_lettered"] == 30
    assert s["depth"] == 0


def test_shutdown_accounting_matches_published_regardless_of_drained_flag():
    # A deliberately tiny timeout: _await_drain gives up almost immediately,
    # so shutdown() returns drained=False. This port's _teardown then clears
    # _running before the pool has drained everything, and _drain's own
    # rescheduling is itself gated on _running - so, unlike a first guess
    # might assume, ThreadPoolExecutor.shutdown(wait=True) does NOT keep
    # draining the rest of the queue in the background: whatever wasn't
    # already popped by an in-flight drain task when _running cleared is
    # simply abandoned, un-popped, sitting in the queue. That's consistent
    # with returning drained=False (the caller is told), not a silent loss -
    # the real invariant is that every published envelope is accounted for
    # by exactly one of delivered / dead_lettered / still-visibly-queued,
    # never uncounted altogether.
    bus = SEDABus(workers=2)
    bus.start()
    bus.channel("d2", capacity=200, concurrency=1)
    bus.subscribe("d2", lambda e: (time.sleep(0.03), True)[-1])
    for i in range(30):
        bus.publish(make_envelope("d2", i))

    drained = bus.shutdown(timeout=0.001)
    assert drained is False
    s = bus.stats()["d2"]
    assert s["delivered"] + s["dead_lettered"] + s["depth"] == 30
    assert s["depth"] > 0  # otherwise this test isn't exercising the timeout path at all


# C5: invalid config must do one documented thing (fail fast or clamp), not
# something unspecified.


def test_channel_config_validation_fails_fast_on_bad_capacity_or_concurrency(bus):
    # This port validates eagerly at construction (raises), unlike most
    # other seda-bus ports, which clamp to a minimum instead - pin that
    # choice down explicitly rather than leaving it implicit/untested.
    with pytest.raises(ValueError):
        bus.channel("bad-capacity", capacity=0)
    with pytest.raises(ValueError):
        bus.channel("bad-concurrency", capacity=10, concurrency=0)


def test_max_attempts_zero_dead_letters_immediately_without_crashing(bus):
    # max_attempts isn't validated at construction (unlike capacity/
    # concurrency, which raise) - pin down what actually happens instead of
    # leaving it untested: `attempt` starts at 1, so `attempt < max_attempts`
    # is never true when max_attempts <= 0, and the first nack dead-letters
    # immediately rather than crashing or looping.
    bus.channel("zero-attempts", capacity=10, max_attempts=0)
    bus.subscribe("zero-attempts", lambda e: False)
    bus.publish(make_envelope("zero-attempts", 1))
    assert _wait(lambda: bus.stats()["zero-attempts"]["dead_lettered"] == 1)


# C6: no resource leak across repeated construct/shutdown cycles.


def test_no_thread_leak_across_repeated_start_shutdown_cycles():
    baseline = threading.active_count()
    for _ in range(25):
        b = SEDABus(workers=4)
        b.start()
        b.channel("warm", capacity=10)
        b.subscribe("warm", lambda e: True)
        b.publish(make_envelope("warm", 1))
        assert b.shutdown(timeout=5) is True

    # Compare against the pre-loop baseline, not a hardcoded number - each
    # start() creates a fresh ThreadPoolExecutor and each shutdown() discards
    # it (bus.py's own design), so this should return to baseline rather
    # than grow with the loop count. A brief settle allows for any
    # non-instantaneous interpreter-level thread teardown.
    assert _wait(lambda: threading.active_count() <= baseline + 2, timeout=5)


def test_concurrent_producers_deliver_exactly_once(bus):
    received: list[int] = []
    lock = threading.Lock()
    bus.channel("fan", capacity=5000, concurrency=8)
    bus.subscribe("fan", lambda e: (lock.acquire(), received.append(e.content()),
                                    lock.release(), True)[-1])

    def producer(base):
        for i in range(500):
            while not bus.publish(make_envelope("fan", base + i), timeout=1.0):
                pass

    threads = [threading.Thread(target=producer, args=(b * 1000,))
               for b in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert _wait(lambda: len(received) == 3000, timeout=15)
    assert len(set(received)) == 3000
