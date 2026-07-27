"""Reader registry: map a raw device identifier to a ReaderSide.

This is the boundary where a physical device becomes a logical "Outside" or
"Inside". After this point the app never touches DeviceMac / DeviceSN again.
"""
from __future__ import annotations

from typing import Dict, Optional

from models import ReaderSide


class ReaderRegistry:
    def __init__(self, mapping: Dict[str, str]):
        # normalize keys so lookups are case-insensitive and colon-agnostic
        self._map: Dict[str, ReaderSide] = {}
        for device_id, side in mapping.items():
            self._map[self._norm(device_id)] = ReaderSide(side)

    @staticmethod
    def _norm(device_id: str) -> str:
        return device_id.strip().upper().replace(":", "").replace("-", "")

    def resolve(self, device_id: Optional[str]) -> Optional[ReaderSide]:
        """Return the ReaderSide for a device id, or None if unknown."""
        if not device_id:
            return None
        return self._map.get(self._norm(device_id))

    def known_ids(self) -> list[str]:
        return list(self._map.keys())
