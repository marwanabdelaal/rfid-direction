"""Direction engine: decide ENTER / EXIT from a reader change.

Kept deliberately tiny and vendor-agnostic. It knows nothing about HTTP,
payloads, or timing internals - it is given the session's first and second
reader and returns a Direction. This is the piece future versions will grow
into a full state machine.
"""
from __future__ import annotations

from typing import Optional

from models import Direction, ReaderSide


class DirectionEngine:
    @staticmethod
    def decide(first: ReaderSide, second: ReaderSide) -> Optional[Direction]:
        """Return the crossing direction, or None if no crossing occurred.

        Outside -> Inside = ENTER
        Inside  -> Outside = EXIT
        Same reader        = None (handled upstream, but guarded here too)
        """
        if first == ReaderSide.OUTSIDE and second == ReaderSide.INSIDE:
            return Direction.ENTER
        if first == ReaderSide.INSIDE and second == ReaderSide.OUTSIDE:
            return Direction.EXIT
        return None
