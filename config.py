"""Configuration loading for the RFID Direction Detection System.

Single responsibility: read config.yaml into a typed, validated object.
Nothing else in the app should read the YAML file directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

import yaml


@dataclass
class Config:
    # raw device-id -> "Outside" / "Inside" (as written in YAML)
    readers: Dict[str, str] = field(default_factory=dict)
    reader_id_field: str = "DeviceMac"

    cooldown_seconds: float = 5.0
    session_timeout_seconds: float = 5.0
    cleanup_interval_seconds: float = 2.0

    host: str = "0.0.0.0"
    port: int = 8000

    log_dir: str = "logs"
    log_level: str = "INFO"


def load_config(path: str | Path = "config.yaml") -> Config:
    """Load and validate configuration from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    cfg = Config(
        readers={str(k): str(v) for k, v in (raw.get("readers") or {}).items()},
        reader_id_field=str(raw.get("reader_id_field", "DeviceMac")),
        cooldown_seconds=float(raw.get("cooldown_seconds", 5)),
        session_timeout_seconds=float(raw.get("session_timeout_seconds", 5)),
        cleanup_interval_seconds=float(raw.get("cleanup_interval_seconds", 2)),
        host=str(raw.get("host", "0.0.0.0")),
        port=int(raw.get("port", 8000)),
        log_dir=str(raw.get("log_dir", "logs")),
        log_level=str(raw.get("log_level", "INFO")),
    )

    if not cfg.readers:
        raise ValueError("Config must define at least one reader under 'readers'.")

    valid_sides = {"Outside", "Inside"}
    for device_id, side in cfg.readers.items():
        if side not in valid_sides:
            raise ValueError(
                f"Reader '{device_id}' has invalid side '{side}'. "
                f"Must be one of {valid_sides}."
            )

    return cfg
