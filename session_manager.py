"""Session manager: the heart of V1 direction detection.

Holds one in-memory Session per EPC and applies the processing rules:

  New tag              -> create session, remember first reader, wait
  Same reader again    -> update last_seen / read_count only, no event
  Reader changes       -> ask DirectionEngine, emit ENTER/EXIT, start cooldown
  During cooldown      -> ignore reads
  Seen by one reader   -> dropped after session_timeout (no event in V1)

Uses a monotonic clock for cooldown/timeout so it is immune to wall-clock
changes. Wall-clock datetimes are carried only for logging.

Thread-safety: process() and cleanup_expired() may run on different threads
(queue worker vs. cleanup task), so mutations are guarded by a lock.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List

from direction_engine import DirectionEngine
from models import DirectionEvent, Session, TagReadEvent

log = logging.getLogger(__name__)

# A subscriber receives DirectionEvent objects. EventLogger is the V1 one.
Subscriber = Callable[[DirectionEvent], None]


class SessionManager:
    def __init__(
        self,
        cooldown_seconds: float,
        session_timeout_seconds: float,
        engine: DirectionEngine | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._cooldown = cooldown_seconds
        self._timeout = session_timeout_seconds
        self._engine = engine or DirectionEngine()
        self._clock = clock
        self._sessions: Dict[str, Session] = {}
        self._subscribers: List[Subscriber] = []
        self._lock = threading.Lock()

    # ---- subscriptions -------------------------------------------------- #
    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    def _publish(self, event: DirectionEvent) -> None:
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception:  # a bad subscriber must not break processing
                log.exception("Subscriber raised while handling event")

    # ---- main entry ----------------------------------------------------- #
    def process(self, event: TagReadEvent) -> None:
        now = self._clock()
        with self._lock:
            session = self._sessions.get(event.epc)

            if session is None:
                self._create_session(event, now)
                return

            # In cooldown after a decision: ignore everything.
            if session.decision_made and now < session.cooldown_until_mono:
                log.debug("EPC %s in cooldown; ignoring read from %s",
                          event.epc, event.reader.value)
                session.last_seen = event.timestamp
                session.last_seen_mono = now
                return

            # Cooldown finished after a previous decision -> start fresh.
            if session.decision_made and now >= session.cooldown_until_mono:
                log.debug("EPC %s cooldown over; starting new session.",
                          event.epc)
                self._create_session(event, now)
                return

            # Same reader again: just update counters, no event.
            if event.reader == session.last_reader:
                session.last_seen = event.timestamp
                session.last_seen_mono = now
                session.read_count += 1
                return

            # Reader changed: decide direction.
            self._handle_reader_change(session, event, now)

    # ---- helpers -------------------------------------------------------- #
    def _create_session(self, event: TagReadEvent, now: float) -> None:
        self._sessions[event.epc] = Session(
            epc=event.epc,
            first_reader=event.reader,
            last_reader=event.reader,
            first_seen=event.timestamp,
            last_seen=event.timestamp,
            read_count=1,
            first_seen_mono=now,
            last_seen_mono=now,
        )
        log.info("New session for EPC %s at %s", event.epc, event.reader.value)

    def _handle_reader_change(
        self, session: Session, event: TagReadEvent, now: float
    ) -> None:
        first = session.first_reader
        second = event.reader
        direction = self._engine.decide(first, second)

        if direction is None:
            # Shouldn't happen with two sides, but stay safe.
            session.last_reader = event.reader
            session.last_seen = event.timestamp
            session.last_seen_mono = now
            session.read_count += 1
            return

        crossing_ms = (now - session.first_seen_mono) * 1000.0

        session.last_reader = second
        session.last_seen = event.timestamp
        session.last_seen_mono = now
        session.read_count += 1
        session.decision_made = True
        session.direction = direction
        session.cooldown_until_mono = now + self._cooldown

        result = DirectionEvent(
            epc=session.epc,
            direction=direction,
            timestamp=datetime.now(),
            crossing_time_ms=crossing_ms,
            first_reader=first,
            second_reader=second,
        )
        self._publish(result)

    # ---- background cleanup -------------------------------------------- #
    def cleanup_expired(self) -> int:
        """Remove single-reader sessions past their timeout and finished
        (cooled-down) sessions. Returns the number removed."""
        now = self._clock()
        removed = 0
        with self._lock:
            for epc in list(self._sessions.keys()):
                s = self._sessions[epc]
                expired_single = (
                    not s.decision_made
                    and (now - s.last_seen_mono) >= self._timeout
                )
                cooldown_done = (
                    s.decision_made and now >= s.cooldown_until_mono
                )
                if expired_single:
                    log.info("Session for EPC %s timed out (single reader).",
                             epc)
                    del self._sessions[epc]
                    removed += 1
                elif cooldown_done:
                    del self._sessions[epc]
                    removed += 1
        return removed

    # ---- introspection (useful for dashboard/tests) -------------------- #
    def active_sessions(self) -> int:
        with self._lock:
            return len(self._sessions)
