"""Demo: a three-stage pipeline plus a parallel-throughput check.

Run under a normal build:      python -m seda_bus
Run free-threaded (parallel):  PYTHON_GIL=0 python3.14t -m seda_bus
"""

from __future__ import annotations

import hashlib
import sys
import time

from ra_common import Envelope

from .bus import Backpressure, Delivery, SEDABus
from .envelope import make_envelope


def _gil_enabled() -> bool:
    is_enabled = getattr(sys, "_is_gil_enabled", None)
    return bool(is_enabled()) if callable(is_enabled) else True


def pipeline_demo() -> None:
    print("\n== pipeline demo ==")
    seen: list[str] = []

    with SEDABus(workers=4) as bus:
        bus.channel("ingest", capacity=100)
        bus.channel("transform", capacity=100)
        bus.channel("sink", capacity=100)

        bus.subscribe("ingest", lambda e: (e.headers.__setitem__("seen_by", "ingest") or True))
        bus.subscribe("transform", lambda e: (e.add_content(e.content().upper()) or True))
        bus.subscribe("sink", lambda e: (seen.append(e.content()) or True))

        done = 0

        def on_complete(_e: Envelope) -> None:
            nonlocal done
            done += 1

        for word in ("alpha", "bravo", "charlie", "delta", "echo"):
            bus.publish(
                make_envelope("ingest", word, slip=["transform", "sink"]),
                on_complete=on_complete,
            )

        deadline = time.monotonic() + 5
        while done < 5 and time.monotonic() < deadline:
            time.sleep(0.01)

        print("completed:", done, "sink saw:", sorted(seen))
        for name, s in bus.stats().items():
            print(f"  {name:<10} {s}")


def parallel_demo() -> None:
    print("\n== parallel throughput ==")
    print("GIL enabled:", _gil_enabled())

    rounds = 12
    work_per_round = 60_000

    def hash_stage(env: Envelope) -> bool:
        acc = b""
        payload = env.content()
        for i in range(work_per_round):
            acc = hashlib.sha256(acc + payload + i.to_bytes(4, "big")).digest()
        env.headers["digest"] = acc.hex()[:8]
        return True

    for concurrency in (1, min(rounds, 8)):
        done = 0

        def on_complete(_e: Envelope) -> None:
            nonlocal done
            done += 1

        with SEDABus(workers=concurrency) as bus:
            bus.channel(
                "hash",
                capacity=rounds,
                concurrency=concurrency,
                backpressure=Backpressure.BLOCK,
                delivery=Delivery.POINT_TO_POINT,
            )
            for _ in range(concurrency):
                bus.subscribe("hash", hash_stage)

            begin = time.monotonic()
            for r in range(rounds):
                bus.publish(make_envelope("hash", f"r{r}".encode()), on_complete=on_complete)
            while done < rounds and time.monotonic() - begin < 120:
                time.sleep(0.005)
            elapsed = time.monotonic() - begin

        print(f"  concurrency={concurrency:>2}  {rounds} rounds in {elapsed:6.2f}s")


if __name__ == "__main__":
    pipeline_demo()
    parallel_demo()
