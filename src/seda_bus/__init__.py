"""seda-bus: a small, broker-less, staged message bus for Python.

Designed to take advantage of free-threaded (PEP 703) CPython, where staged
CPU-bound work finally runs in parallel across cores. Works on a normal GIL
build too (I/O-bound stages still parallelise; CPU-bound stages serialise).

The bus carries :class:`ra_common.Envelope` (the same wrapper ``seda-bus-java``
uses via ``ra-common-java``); routing follows the envelope's
``DynamicRoutingSlip``. :func:`make_envelope` keeps the ergonomic
``to`` / ``payload`` / ``slip`` shape.
"""

from .bus import Backpressure, Channel, Consumer, Delivery, SEDABus
from .envelope import Envelope, make_envelope, target_service

__version__ = "0.2.0"

__all__ = [
    "SEDABus",
    "Channel",
    "Consumer",
    "Delivery",
    "Backpressure",
    "Envelope",
    "make_envelope",
    "target_service",
    "__version__",
]
