"""Normalized internal data models.

These are the only objects the business logic (session manager, direction
engine, logger) is allowed to work with. The raw vendor payload lives only
inside parser.py and never leaves it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ReaderSide(Enum):
    """Physical side of the doorway a reader sits on."""
    OUTSIDE = "Outside"
    INSIDE = "Inside"


class Direction(Enum):
    """Outcome of a crossing decision."""
    ENTER = "ENTER"
    EXIT = "EXIT"


@dataclass
class TagReadEvent:
    """A single normalized read from one reader for one tag.

    This is the vendor-agnostic unit that flows through the queue.
    """
    epc: str
    reader: ReaderSide
    timestamp: datetime
    rssi: int


@dataclass
class Session:
    """Per-EPC tracking state. Lives in memory only."""
    epc: str
    first_reader: ReaderSide
    last_reader: ReaderSide
    first_seen: datetime
    last_seen: datetime
    read_count: int = 1
    decision_made: bool = False
    direction: Optional[Direction] = None
    # monotonic timestamps used for cooldown / timeout math (wall clock is
    # only for logging and display).
    first_seen_mono: float = 0.0
    last_seen_mono: float = 0.0
    cooldown_until_mono: float = 0.0


@dataclass
class DirectionEvent:
    """A domain event emitted when a crossing is decided.

    Future components (dashboard, MQTT, database) subscribe to these.
    """
    epc: str
    direction: Direction
    timestamp: datetime          # when the decision was made
    crossing_time_ms: float      # elapsed between first and second reader
    first_reader: ReaderSide = field(default=ReaderSide.OUTSIDE)
    second_reader: ReaderSide = field(default=ReaderSide.INSIDE)
