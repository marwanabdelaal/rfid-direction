"""Offline test harness for the direction logic — no reader hardware needed.

Two modes:
  python simulate.py          run the pipeline in-process against a fake clock
  python simulate.py --http    POST sample batches to a running server

The in-process mode drives SessionManager directly with a controllable clock
so cooldown/timeout behaviour is deterministic, and asserts the expected
ENTER/EXIT results.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

from direction_engine import DirectionEngine
from models import Direction, ReaderSide, TagReadEvent
from session_manager import SessionManager


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _event(epc: str, side: ReaderSide, when: datetime, rssi: int = -50):
    return TagReadEvent(epc=epc, reader=side, timestamp=when, rssi=rssi)


def run_offline() -> int:
    clock = FakeClock()
    captured: list = []

    sm = SessionManager(
        cooldown_seconds=5,
        session_timeout_seconds=5,
        engine=DirectionEngine(),
        clock=clock,
    )
    sm.subscribe(captured.append)

    base = datetime(2026, 7, 27, 12, 30, 0)
    failures = 0

    def check(name: str, cond: bool) -> None:
        nonlocal failures
        status = "PASS" if cond else "FAIL"
        if not cond:
            failures += 1
        print(f"  [{status}] {name}")

    # --- Case 1: Outside -> Inside = ENTER ------------------------------- #
    print("Case 1: Outside -> Inside should be ENTER")
    sm.process(_event("TAG1", ReaderSide.OUTSIDE, base))
    clock.advance(0.8)
    sm.process(_event("TAG1", ReaderSide.INSIDE, base + timedelta(milliseconds=800)))
    check("one event emitted", len(captured) == 1)
    check("direction is ENTER", captured and captured[-1].direction == Direction.ENTER)
    check("crossing ~800ms", captured and 700 <= captured[-1].crossing_time_ms <= 900)

    # --- Case 2: cooldown suppresses duplicate --------------------------- #
    print("Case 2: reads during cooldown produce no new event")
    clock.advance(1.0)  # still within 5s cooldown
    sm.process(_event("TAG1", ReaderSide.OUTSIDE, base + timedelta(seconds=2)))
    check("still one event", len(captured) == 1)

    # --- Case 3: Inside -> Outside = EXIT (new tag) ---------------------- #
    print("Case 3: Inside -> Outside should be EXIT")
    sm.process(_event("TAG2", ReaderSide.INSIDE, base))
    clock.advance(0.5)
    sm.process(_event("TAG2", ReaderSide.OUTSIDE, base + timedelta(milliseconds=500)))
    check("two events total", len(captured) == 2)
    check("direction is EXIT", captured[-1].direction == Direction.EXIT)

    # --- Case 4: same reader repeats = no event -------------------------- #
    print("Case 4: repeated same-reader reads produce no event")
    before = len(captured)
    sm.process(_event("TAG3", ReaderSide.OUTSIDE, base))
    sm.process(_event("TAG3", ReaderSide.OUTSIDE, base))
    sm.process(_event("TAG3", ReaderSide.OUTSIDE, base))
    check("no new event", len(captured) == before)
    check("read_count == 3", sm._sessions["TAG3"].read_count == 3)

    # --- Case 5: single-reader session times out ------------------------- #
    print("Case 5: single-reader session is cleaned up after timeout")
    check("TAG3 session exists", "TAG3" in sm._sessions)
    clock.advance(6.0)  # past 5s timeout
    removed = sm.cleanup_expired()
    check("cleanup removed session(s)", removed >= 1)
    check("TAG3 gone", "TAG3" not in sm._sessions)
    check("still two events (no phantom)", len(captured) == 2)

    print()
    if failures == 0:
        print("ALL CHECKS PASSED")
    else:
        print(f"{failures} CHECK(S) FAILED")
    return failures


def run_http() -> int:
    import json
    import urllib.request

    url = "http://localhost:8000/rfid"

    def post(batch):
        data = json.dumps(batch).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            print("  ->", resp.read().decode())

    mac_out = "84:D8:1B:12:34:56"
    mac_in = "84:D8:1B:65:43:21"
    now = datetime.now().isoformat(timespec="milliseconds")

    print("POST Outside read for TAGHTTP")
    post([{"TagID": "TAGHTTP", "TimeStamp": now,
           "DeviceMac": mac_out, "Rssi": "-52"}])
    print("POST Inside read for TAGHTTP (should log ENTER on the server)")
    post([{"TagID": "TAGHTTP", "TimeStamp": now,
           "DeviceMac": mac_in, "Rssi": "-49"}])
    print("Check the server console / logs/events.log for the ENTER block.")
    return 0


if __name__ == "__main__":
    if "--http" in sys.argv:
        sys.exit(run_http())
    sys.exit(run_offline())
