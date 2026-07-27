"""Logging setup and the event logger.

Three log destinations per the spec:
    logs/app.log     - general application log
    logs/events.log  - one structured block per ENTER/EXIT decision
    logs/errors.log  - warnings and errors

Nothing in the app prints directly; decisions become DirectionEvent objects
that are handed here to be logged (and, in future, republished).
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from models import DirectionEvent

_MAX_BYTES = 5 * 1024 * 1024
_BACKUPS = 3


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    """Configure the app, events and errors loggers. Call once at startup."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_level = getattr(logging, level.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ---- app logger (root) : console + app.log ----
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    app_fh = RotatingFileHandler(
        Path(log_dir) / "app.log", maxBytes=_MAX_BYTES, backupCount=_BACKUPS
    )
    app_fh.setFormatter(fmt)
    root.addHandler(app_fh)

    # ---- errors.log : WARNING and above ----
    err_fh = RotatingFileHandler(
        Path(log_dir) / "errors.log", maxBytes=_MAX_BYTES, backupCount=_BACKUPS
    )
    err_fh.setFormatter(fmt)
    err_fh.setLevel(logging.WARNING)
    root.addHandler(err_fh)

    # ---- events.log : dedicated, plain message format ----
    events = logging.getLogger("events")
    events.setLevel(logging.INFO)
    events.propagate = False
    events.handlers.clear()
    ev_fh = RotatingFileHandler(
        Path(log_dir) / "events.log", maxBytes=_MAX_BYTES, backupCount=_BACKUPS
    )
    ev_fh.setFormatter(logging.Formatter("%(message)s"))
    events.addHandler(ev_fh)
    # also echo events to console
    events.addHandler(console)


class EventLogger:
    """Consumes DirectionEvent objects and writes structured log blocks.

    This is the single subscriber in V1. Additional subscribers (dashboard,
    MQTT, DB) can be attached the same way in future versions.
    """

    def __init__(self) -> None:
        self._events = logging.getLogger("events")

    def emit(self, event: DirectionEvent) -> None:
        block = (
            f"[{event.timestamp.strftime('%H:%M:%S.%f')[:-3]}]\n"
            f"EPC: {event.epc}\n"
            f"First Reader: {event.first_reader.value}\n"
            f"Second Reader: {event.second_reader.value}\n"
            f"Elapsed: {event.crossing_time_ms:.0f} ms\n"
            f"Decision: {event.direction.value}\n"
        )
        self._events.info(block)
