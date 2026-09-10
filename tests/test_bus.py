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
