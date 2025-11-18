Staged Event-Driven Architecture Bus - A form of message bus avoiding the high overhead of thread-based concurrency 
models where channels get their own inbound and outbound queues.

**IN-PROGRESS**

NOTES
+ MUST use free-threaded (-nogil) version of Python.
  + Install: sudo apt-get install python3.14-nogil
  + Verify: python3.14-nogil -VV
  + Test: seda-bus/parallel_verify.py
    + Use python3.14 first to verify sequential processing
    + Switch to -nogil to verify parallel processing
    + Use interpreter parameter PYTHON_GIL=0 to disable GIL
    + Tests:
      + 1: 1 worker, 400k work total
        + 3.14: 0.77 seconds
        + 3.14t (GIL Disabled): 0.99 seconds
      + 2: 4 workers, 400k work total (100k per worker)
        + 3.14: 4.01 seconds
        + 3.14t (GIL Disabled): 1.02 seconds
      + 3: 12 workers, 400k work total (30k per worker)
        + 3.14: 5.70 seconds
        + 3.14t (GIL Disabled): 1.50 seconds