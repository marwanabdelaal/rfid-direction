"""Application entry point / composition root.

Wires all modules together and starts the FastAPI server. Each module has a
single responsibility; this file is where they are assembled:

    config -> registry -> parser
                       -> session_manager -> event_logger (subscriber)
                       -> queue_worker (drains queue + cleanup thread)
                       -> http_listener (FastAPI routes)

Run:
    python app.py
or:
    uvicorn app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import load_config
from direction_engine import DirectionEngine
from http_listener import build_router
from logger import EventLogger, setup_logging
from parser import PayloadParser
from queue_worker import QueueWorker
from reader_registry import ReaderRegistry
from session_manager import SessionManager

log = logging.getLogger(__name__)


def create_app(config_path: str = "config.yaml") -> FastAPI:
    cfg = load_config(config_path)
    setup_logging(cfg.log_dir, cfg.log_level)

    registry = ReaderRegistry(cfg.readers)
    parser = PayloadParser(registry, cfg.reader_id_field)

    session_manager = SessionManager(
        cooldown_seconds=cfg.cooldown_seconds,
        session_timeout_seconds=cfg.session_timeout_seconds,
        engine=DirectionEngine(),
    )
    session_manager.subscribe(EventLogger().emit)

    worker = QueueWorker(session_manager, cfg.cleanup_interval_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker.start()
        log.info(
            "RFID Direction System V1.0 ready. Readers: %s",
            ", ".join(registry.known_ids()),
        )
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title="RFID Direction Detection System", version="1.0",
                  lifespan=lifespan)
    app.include_router(build_router(parser, worker))

    # stash config so `python app.py` can read host/port
    app.state.config = cfg
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    cfg = app.state.config
    uvicorn.run(app, host=cfg.host, port=cfg.port)
