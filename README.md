# Staged Event-Driven Architecture Bus
A form of message bus avoiding the high overhead of thread-based concurrency 
models where channels get their own inbound and outbound queues.

**IN-PROGRESS**

NOTES
+ MUST use free-threaded (-nogil) version of Python.
+ Install: sudo apt-get install python3.14-nogil
+ Verify Version: python3.14-nogil -VV
+ Verify Parallelization: seda-bus/parallel_verify.py
  + Use python3.14 first to verify sequential processing
    + Install: sudo apt-get install python3.14 
    + Verify Version: python3.14 -VV
  + Switch to -nogil to verify parallel processing
    + Use interpreter parameter PYTHON_GIL=0 to disable GIL
  + Tests:
    + 18 Difficulty
      + 1: 1 worker, 12 resources
        + 3.10: 1.84 seconds
        + 3.14: 2.26 seconds
        + 3.14t (GIL Disabled): 3.85 seconds
      + 2: 4 workers, 3 resources per worker (12 resources total)
        + 3.10: 8.55 seconds
        + 3.14: 7.39 seconds
        + 3.14t (GIL Disabled): 1.57 seconds
      + 3: 12 workers, 1 resource per worker (12 resources total)
        + 3.10: 8.13 seconds
        + 3.14: 6.51 seconds
        + 3.14t (GIL Disabled): 1.2 seconds
    + 20 Difficulty
      + 1: 1 worker, 12 resources
        + 3.10: 13.36 seconds
        + 3.14: 12.62 seconds
        + 3.14t (GIL Disabled): 10.62 seconds
      + 2: 4 workers, 3 resources per worker (12 resources total)
        + 3.10: 22.27 seconds
        + 3.14: 13.75 seconds
        + 3.14t (GIL Disabled): 5.17 seconds
      + 3: 12 workers, 1 resource per worker (12 resources total)
        + 3.10: 25.47 seconds
        + 3.14: 19.48 seconds
        + 3.14t (GIL Disabled): 4.08 seconds