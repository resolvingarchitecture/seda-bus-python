"""The unit of work that moves through the bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class Envelope:
    """A message addressed to a channel.

    ``to`` is the channel the envelope is currently headed for. ``slip`` is an
    ordered list of channel names to visit after the current one (a routing
    slip / itinerary). ``attempts`` counts delivery attempts on the current
    hop and is used for retry / dead-lettering.
    """

    to: str
    payload: Any = None
    id: str = field(default_factory=lambda: uuid4().hex)
    sender: str | None = None
    headers: dict[str, Any] = field(default_factory=dict)
    slip: list[str] = field(default_factory=list)
    attempts: int = 0

    def advance(self) -> bool:
        """Move to the next hop in the routing slip.

        Returns ``True`` if there was another hop (``to`` now points at it and
        ``attempts`` is reset), ``False`` if the itinerary is complete.
        """
        if not self.slip:
            return False
        self.to = self.slip.pop(0)
        self.attempts = 0
        return True
