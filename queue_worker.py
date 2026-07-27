"""Queue worker: decouples HTTP intake from processing.

The HTTP endpoint must return fast, so it only normalizes reads and drops
them on this queue. A background worker thread drains the queue and feeds
events to the SessionManager sequentially (order matters for direction).

A separate cleanup thread periodically purges expired sessions using
monotonic timers.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import List

from models import TagReadEvent
from session_manager import SessionManager

log = logging.getLogger(__name__)


class QueueWorker:
    def __init__(
        self,
        session_manager: SessionManager,
        cleanup_interval_seconds: float,
    ):
        self._sm = session_manager
        self._cleanup_interval = cleanup_interval_seconds
        self._q: "queue.Queue[TagReadEvent]" = queue.Queue()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._cleaner: threading.Thread | None = None

    # ---- lifecycle ------------------------------------------------------ #
    def start(self) -> None:
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._run_worker, name="queue-worker", daemon=True
        )
        self._cleaner = threading.Thread(
            target=self._run_cleaner, name="session-cleaner", daemon=True
        )
        self._worker.start()
        self._cleaner.start()
        log.info("Queue worker and cleanup task started.")

    def stop(self) -> None:
        self._stop.set()
        # unblock the worker's queue.get
        self._q.put(None)  # type: ignore[arg-type]
        for t in (self._worker, self._cleaner):
            if t is not None:
                t.join(timeout=2.0)
        log.info("Queue worker stopped.")

    # ---- producer side (called from HTTP handler) ---------------------- #
    def enqueue_batch(self, events: List[TagReadEvent]) -> None:
        for event in events:
            self._q.put(event)

    def pending(self) -> int:
        return self._q.qsize()

    # ---- consumer threads ---------------------------------------------- #
    def _run_worker(self) -> None:
        while not self._stop.is_set():
            event = self._q.get()
            if event is None:  # sentinel from stop()
                self._q.task_done()
                break
            try:
                self._sm.process(event)
            except Exception:
                log.exception("Error processing event for EPC %s",
                              getattr(event, "epc", "?"))
            finally:
                self._q.task_done()

    def _run_cleaner(self) -> None:
        while not self._stop.wait(self._cleanup_interval):
            try:
                removed = self._sm.cleanup_expired()
                if removed:
                    log.debug("Cleanup removed %d session(s).", removed)
            except Exception:
                log.exception("Error during session cleanup")
