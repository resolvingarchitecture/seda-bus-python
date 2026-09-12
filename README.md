# seda-bus (Python)

A small, broker-less, **staged** message bus. Work is decomposed into stages
(`Channel`s) connected by bounded queues; a single shared worker pool drains
them; each stage has its own concurrency limit so none can monopolise the pool.

```python
from seda_bus import SEDABus, make_envelope, Delivery

with SEDABus(workers=8) as bus:
    bus.channel("ingest",    capacity=1000)
    bus.channel("transform", capacity=1000, concurrency=4)
    bus.channel("sink",      capacity=1000)

    bus.subscribe("ingest",    lambda e: True)
    bus.subscribe("transform", lambda e: (e.add_content(e.content().upper()), True)[1])
    bus.subscribe("sink",      lambda e: (print(e.content()), True)[1])

    bus.publish(
        make_envelope("ingest", "hello", slip=["transform", "sink"]),
        on_complete=lambda e: print("done", e.id),
    )
```

The bus carries [`ra_common.Envelope`](https://github.com/resolvingarchitecture/ra-common-python)
— the same wrapper `seda-bus-java` uses via `ra-common-java`. Routing follows the
envelope's `DynamicRoutingSlip` (LIFO, keyed by `route.service`);
`make_envelope(to, payload, slip=[...])` keeps the earlier ergonomic shape, and
`target_service(env)` is the channel an envelope is currently headed for.

## Why this exists

SEDA's staged-concurrency model — many CPU-bound stages, each with its own
queue, all fed by one thread pool — was **pointless in CPython under the GIL**:
threads don't run Python bytecode in parallel, so you reached for
`multiprocessing` (IPC + pickling costs) or `asyncio` (only helps I/O-bound
stages).

Free-threaded CPython (PEP 703; experimental in 3.13, improved in 3.14) is the
first build where the model is a good fit for pure-Python stages. This repo is a
working demonstration of that, plus the measurements behind it.

## Measurements

**The bus itself**, 24 CPU-bound hashing envelopes through one stage, 12-core
machine, `python3.14` vs `python3.14t` (`PYTHON_GIL=0`):

| workers | 3.14 (GIL) | 3.14t (free-threaded) |
|--------:|-----------:|----------------------:|
| 1       | 0.54 s     | 0.71 s                |
| 4       | 0.78 s     | 0.35 s                |
| 12      | 0.79 s     | 0.27 s                |

Under the GIL, adding workers makes it *slower* (contention, no parallelism).
Free-threaded, it scales ~2.6× across the pool — after paying a ~1.3× single-thread
tax (free-threaded builds lose the specialising adaptive interpreter and add
per-object locking; the gap is closing release over release).

**Raw interpreter** (no bus — `bench/bench_sha.py`, `bench/bench_hashcash.py`),
earlier runs on the same machine:

| workload | 3.14 (GIL) | 3.14t | speedup |
|---|---:|---:|---:|
| SHA-1, 1 worker, 1.2M hashes | 1.33 s | 1.97 s | 0.67× |
| SHA-1, 4 workers | 3.14 s | 0.61 s | 5.1× |
| SHA-1, 12 workers | 3.25 s | 0.48 s | 6.8× |
| hashcash-18, 12 workers | 6.51 s | 1.20 s | 5.4× |

The bus's speedup is lower than the raw interpreter's because a real staged bus
pays for queue locks, permits, and scheduling. That coordination cost is the
point of measuring it end-to-end rather than trusting the microbenchmark.

## What this is / isn't

**Is:** bounded per-stage queues (admission control), a back-pressure policy per
stage (`BLOCK` / `REJECT` / `DROP_NEWEST` / `DROP_OLDEST`), per-stage concurrency
limits, point-to-point (round-robin) or pub/sub delivery, routing slips
(itineraries), retry + dead-letter channels, per-stage metrics, graceful
shutdown that drains.

**Isn't (yet):** SEDA's original *adaptive controller* — the part that watched
per-stage latency and queue depth at runtime and re-tuned thread allocation and
shed load automatically. Everything here is static configuration. The controller
is the interesting next step and the reason the model is worth revisiting now
that free-threading makes it matter.

## Layout

```
src/seda_bus/        the library (stdlib only)
  envelope.py        the unit of work
  bus.py             SEDABus, Channel, WorkerPool, policies
  __main__.py        `python -m seda_bus` demo
tests/               pytest correctness + parallel-scaling tests
bench/               the raw interpreter microbenchmarks
```

## Running

```sh
# correctness (any build)
PYTHONPATH=src python -m pytest tests/

# the demo
python -m seda_bus
PYTHON_GIL=0 python3.14t -m seda_bus        # free-threaded

# free-threaded Python
sudo apt install python3.14-nogil           # or build with --disable-gil
python3.14t -VV
```

## Correctness suite coverage

See `../CORRECTNESS_SUITE.md` for what C1–C7 mean; every port implements
the same checklist in its own idiom. This port's coverage, all in
`tests/test_bus.py` unless noted:

| # | Property | Test(s) |
|---|----------|---------|
| C1 | Backpressure: Reject | `test_backpressure_reject_when_full` |
| C1 | Backpressure: Block | `test_backpressure_block_waits_for_room` |
| C1 | Backpressure: DropNewest | `test_backpressure_drop_newest_matches_reject` |
| C1 | Backpressure: DropOldest | `test_backpressure_drop_oldest_evicts_instead_of_rejecting` |
| C2 | Retry exhausts to dead-letter | `test_nack_retries_then_dead_letters` |
| C2 | Retry succeeds on final attempt, attempt state cleared | `test_nack_retry_succeeds_on_final_attempt_and_clears_attempt_state` |
| C2 | No consumers dead-letters immediately | `test_channel_with_no_consumers_dead_letters_immediately` |
| C3 | Consumer exception isolation | `test_consumer_exception_isolation` |
| C4 | Shutdown accounting, drained in time | `test_shutdown_accounting_matches_published_when_drained_in_time` |
| C4 | Shutdown accounting, timeout expires first | `test_shutdown_accounting_matches_published_regardless_of_drained_flag` |
| C5 | Config validation (fails fast on `capacity`/`concurrency` &lt; 1) | `test_channel_config_validation_fails_fast_on_bad_capacity_or_concurrency` |
| C5 | `max_attempts &lt;= 0` is defined (immediate dead-letter, not a crash) | `test_max_attempts_zero_dead_letters_immediately_without_crashing` |
| C6 | No thread leak across repeated start/shutdown cycles | `test_no_thread_leak_across_repeated_start_shutdown_cycles` |
| C7 | Exactly-once under concurrent producers | `test_concurrent_producers_deliver_exactly_once` |

Verified on CPython 3.13.8 (the working `.venv`); 3.14 free-threaded
verification for this specific suite is covered separately by
`tests/test_parallel.py` (CPU-bound scaling), not re-run for C1–C6 here.

## Companion implementations

Same design, other languages:

* [seda-bus](https://github.com/resolvingarchitecture/seda-bus) — Rust, zero-dependency, real shared thread pool
* [seda-bus-java](https://github.com/resolvingarchitecture/seda-bus-java) — Java, with optional guaranteed-delivery persistence
* [seda-bus-ts](https://github.com/resolvingarchitecture/seda-bus-ts) — TypeScript / Node, event-loop model

## Status

`0.1.0` — working core, tested. Not published to PyPI yet.
