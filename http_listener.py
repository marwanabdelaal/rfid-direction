"""FastAPI HTTP listener.

Thin transport layer. Its only jobs:
  - accept POSTs from the readers,
  - hand the raw body to the parser,
  - enqueue the normalized events,
  - return immediately.

No business logic lives here.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from parser import PayloadParser
from queue_worker import QueueWorker

log = logging.getLogger(__name__)


def build_router(parser: PayloadParser, worker: QueueWorker) -> APIRouter:
    router = APIRouter()

    @router.post("/rfid")
    async def receive_reads(request: Request) -> dict[str, Any]:
        """Endpoint both readers POST to."""
        try:
            payload = await request.json()
        except Exception:
            log.warning("Received non-JSON or empty body.")
            return {"status": "error", "reason": "invalid json", "accepted": 0}

        events = parser.parse_batch(payload)
        worker.enqueue_batch(events)
        return {"status": "ok", "accepted": len(events), "pending": worker.pending()}

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "pending": worker.pending()}

    return router
