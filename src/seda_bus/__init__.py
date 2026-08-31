"""seda-bus: a small, broker-less, staged message bus for Python.

Designed to take advantage of free-threaded (PEP 703) CPython, where staged
CPU-bound work finally runs in parallel across cores. Works on a normal GIL
build too (I/O-bound stages still parallelise; CPU-bound stages serialise).
"""

from .bus import Backpressure, Channel, Consumer, Delivery, SEDABus
from .envelope import Envelope

__version__ = "0.1.0"

__all__ = [
    "SEDABus",
    "Channel",
    "Consumer",
    "Delivery",
    "Backpressure",
    "Envelope",
    "__version__",
]
