"""Envelope helpers.

The bus carries :class:`ra_common.Envelope` (the same wrapper ``seda-bus-java``
uses via ``ra-common-java``). Routing is driven by the envelope's
``DynamicRoutingSlip``: each hop targets ``route.service``; the slip is walked
one hop at a time with :meth:`ra_common.Envelope.ratchet`.

These helpers keep the ergonomic ``Envelope(to=..., payload=..., slip=[...])``
shape from earlier seda-bus versions on top of the richer ra-common type.
"""

from __future__ import annotations

from typing import Any, Iterable

from ra_common import Envelope

__all__ = ["Envelope", "make_envelope", "target_service", "envelope_payload", "set_payload"]

#: operation stamped on the routes seda-bus creates (seda-bus routes by service,
#: not operation; ra-common still wants a value there).
_OP = "RECEIVE"


def make_envelope(
    to: str,
    payload: Any = None,
    *,
    slip: Iterable[str] = (),
    sender: str | None = None,
    headers: dict[str, Any] | None = None,
) -> Envelope:
    """Build a document envelope addressed to channel ``to``, then visiting each
    name in ``slip`` in order."""
    env = Envelope.document()
    # ra-common slips are LIFO: push the itinerary tail-first, then ``to`` last,
    # so ``next_route()`` yields ``to``, then slip[0], slip[1], ...
    for name in reversed(list(slip)):
        env.add_route(name, _OP)
    env.add_route(to, _OP)
    if payload is not None:
        env.add_content(payload)
    if sender is not None:
        env.client = sender
    if headers:
        env.headers.update(headers)
    return env


def target_service(env: Envelope) -> str | None:
    """The channel name the envelope is currently headed for."""
    route = env.get_route()
    return route.service if route is not None else None


def envelope_payload(env: Envelope) -> Any:
    """The document ``CONTENT`` value (what :func:`make_envelope` stored)."""
    return env.content()


def set_payload(env: Envelope, payload: Any) -> None:
    env.add_content(payload)
