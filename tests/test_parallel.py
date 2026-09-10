"""Does the bus itself scale across cores?

Pushes CPU-bound stages through the bus and compares wall time at
concurrency 1 vs N. On a free-threaded build this should show real speedup;
on a GIL build it will not (and the test only asserts correctness there).
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
import time

import pytest

from seda_bus import Envelope, SEDABus, make_envelope


def _gil_enabled() -> bool:
    is_enabled = getattr(sys, "_is_gil_enabled", None)
    return bool(is_enabled()) if callable(is_enabled) else True


def _cpu_work(payload: bytes, iterations: int) -> str:
    acc = payload
    for i in range(iterations):
        acc = hashlib.sha256(acc + i.to_bytes(4, "big")).digest()
    return acc.hex()[:8]


def _run(concurrency: int, rounds: int, iterations: int) -> float:
    done = threading.Semaphore(0)

    def stage(env: Envelope) -> bool:
        env.headers["digest"] = _cpu_work(env.content(), iterations)
        done.release()
        return True

    bus = SEDABus(workers=concurrency)
    bus.start()
    try:
        bus.channel("hash", capacity=rounds, concurrency=concurrency)
        for _ in range(concurrency):
            bus.subscribe("hash", stage)

        begin = time.monotonic()
        for r in range(rounds):
            assert bus.publish(make_envelope("hash", f"r{r}".encode()))
        for _ in range(rounds):
            assert done.acquire(timeout=120)
        return time.monotonic() - begin
    finally:
        bus.shutdown(timeout=10)


def test_bus_delivers_all_cpu_bound_work():
    assert _run(concurrency=4, rounds=16, iterations=5_000) > 0


@pytest.mark.skipif(_gil_enabled(), reason="needs a free-threaded build")
@pytest.mark.skipif((os.cpu_count() or 1) < 4, reason="needs >= 4 cores")
def test_bus_scales_without_the_gil():
    rounds, iterations = 24, 40_000
    serial = _run(concurrency=1, rounds=rounds, iterations=iterations)
    parallel = _run(concurrency=4, rounds=rounds, iterations=iterations)
    # Expect a solid speedup; be conservative to avoid CI flakiness.
    assert parallel < serial * 0.6, f"serial={serial:.2f}s parallel={parallel:.2f}s"
