Staged Event-Driven Architecture Bus - A form of message bus avoiding the high overhead of thread-based concurrency 
models where channels get their own inbound and outbound queues.

NOTES
+ MUST use free-threaded (-nogil) version of Python.
  + Install: sudo apt-get install python3.14-nogil
  + Verify: python3.14-nogil -VV
  + Test: seda-bus/parallel_verify.py
    + Use python3.10 first to verify sequential processing
    + Switch to -nogil to verify parallel processing
    + Test 1:
      + 3.10: 3.46 seconds
      + 3.14t: 1.09 seconds