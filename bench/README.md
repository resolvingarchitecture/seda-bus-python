# Benchmarks

Raw interpreter microbenchmarks (no bus) used to check whether free-threaded
CPython actually parallelises this kind of CPU-bound work.

```sh
python3.14  bench/bench_sha.py        # GIL baseline
PYTHON_GIL=0 python3.14t bench/bench_sha.py
PYTHON_GIL=0 python3.14t bench/bench_hashcash.py
```

`hashcash.py` is a vendored hashcash implementation (beer-ware license, Anton
Bobrov) used by `bench_hashcash.py`.
