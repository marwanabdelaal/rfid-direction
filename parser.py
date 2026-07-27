"""Vendor payload parser (adapter).

This is the ONLY module that understands the Hopeland UHF reader payload.
It turns raw JSON items into normalized TagReadEvent objects. If the vendor
format changes, only this file changes.

Expected raw item (from spec, C# UhfTagReadings):
    {
      "TagID":         "300833B2DDD9014000000001",
      "TimeStamp":     "2026-07-27T12:30:01.235",
      "AntennaNumber": "1",
      "DeviceMac":     "84:D8:1B:12:34:56",
      "Rssi":          "-52",
      "DeviceSN":      "SN12345"
    }
The exact JSON format will be finalized later; keep parsing tolerant.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional

from models import TagReadEvent
from reader_registry import ReaderRegistry

log = logging.getLogger(__name__)


class PayloadParser:
    def __init__(self, registry: ReaderRegistry, reader_id_field: str = "DeviceMac"):
        self._registry = registry
        self._reader_id_field = reader_id_field

    def parse_batch(self, payload: Any) -> List[TagReadEvent]:
        """Normalize a POST payload (a list of raw readings) into events.

        Unknown readers and malformed items are skipped with a warning rather
        than aborting the whole batch.
        """
        items = self._as_list(payload)
        events: List[TagReadEvent] = []
        for item in items:
            event = self._parse_item(item)
            if event is not None:
                events.append(event)
        # Sort by timestamp so ordering is deterministic regardless of how the
        # reader batched the reads.
        events.sort(key=lambda e: e.timestamp)
        return events

    # ------------------------------------------------------------------ #
    def _as_list(self, payload: Any) -> List[dict]:
        if isinstance(payload, list):
            return [p for p in payload if isinstance(p, dict)]
        if isinstance(payload, dict):
            # tolerate {"readings": [...]} or a single object
            for key in ("readings", "tags", "data", "items"):
                if isinstance(payload.get(key), list):
                    return [p for p in payload[key] if isinstance(p, dict)]
            return [payload]
        return []

    def _parse_item(self, item: dict) -> Optional[TagReadEvent]:
        epc = self._first(item, "TagID", "tagId", "epc", "EPC")
        if not epc:
            log.warning("Skipping item with no TagID: %s", item)
            return None

        device_id = self._first(item, self._reader_id_field, "DeviceMac",
                                 "DeviceSN", "deviceMac", "deviceSn")
        reader = self._registry.resolve(device_id)
        if reader is None:
            log.warning("Unknown reader id '%s' for EPC %s; skipping.",
                        device_id, epc)
            return None

        ts = self._parse_timestamp(self._first(item, "TimeStamp", "timestamp"))
        rssi = self._parse_int(self._first(item, "Rssi", "rssi"))

        return TagReadEvent(
            epc=str(epc).strip().upper(),
            reader=reader,
            timestamp=ts,
            rssi=rssi,
        )

    @staticmethod
    def _first(item: dict, *keys: str) -> Optional[Any]:
        for k in keys:
            if k in item and item[k] not in (None, ""):
                return item[k]
        return None

    @staticmethod
    def _parse_timestamp(raw: Optional[Any]) -> datetime:
        if raw is None:
            return datetime.now()
        s = str(raw).strip()
        # try ISO 8601 first (handles trailing Z)
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                    "%Y/%m/%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        log.warning("Unparseable timestamp '%s'; using now().", raw)
        return datetime.now()

    @staticmethod
    def _parse_int(raw: Optional[Any]) -> int:
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return 0
