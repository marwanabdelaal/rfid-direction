# RFID Direction Detection System — Version 1.0

A lightweight FastAPI application for a Raspberry Pi that receives HTTP POSTs
from two Hopeland UHF RFID readers and decides whether a tagged person
**entered** or **exited** a doorway.

Version 1.0 does **only** reliable IN/OUT detection. The architecture is
deliberately modular so future features (occupancy counting, reverse/approach
detection, dashboard, persistence, MQTT) can be added without refactoring.

## How it decides direction

Two readers sit ~1.5 m either side of the door and independently POST their
reads. The system tracks the order a tag hits the two sides:

| Sequence            | Result |
|---------------------|--------|
| Outside → Inside    | ENTER  |
| Inside → Outside    | EXIT   |
| Same reader repeats | counters updated only, no event |
| Seen by one reader  | session dropped after timeout, no event (V1) |

After any ENTER/EXIT decision, a **cooldown** (default 5 s) suppresses further
reads so a lingering person isn't counted twice.

## Architecture

```
Readers ──HTTP POST──▶ http_listener (FastAPI)
                           │
                           ▼
                        parser  ── uses ──▶ reader_registry (MAC → side)
                           │
                           ▼  normalized TagReadEvent
                     queue_worker (background thread)
                           │
                           ▼
                     session_manager ── uses ──▶ direction_engine
                           │  emits DirectionEvent
                           ▼
                     logger (EventLogger subscriber)
                           │
                           ▼
             console · events.log · (future: dashboard / DB / MQTT)
```

Only `parser.py` understands the vendor payload. Everything downstream works
with the normalized `TagReadEvent` / `DirectionEvent` models.

## Files

| File | Responsibility |
|------|----------------|
| `app.py` | Composition root; wires modules, starts server |
| `config.py` / `config.yaml` | Load & validate configuration |
| `http_listener.py` | FastAPI routes; enqueue and return fast |
| `parser.py` | Vendor adapter: raw payload → `TagReadEvent` |
| `reader_registry.py` | Device MAC/SN → `ReaderSide` |
| `queue_worker.py` | Queue drain + periodic session cleanup |
| `session_manager.py` | Per-EPC sessions, cooldown, timeout |
| `direction_engine.py` | ENTER/EXIT decision logic |
| `models.py` | Normalized dataclasses / enums |
| `logger.py` | App/events/errors logs + `EventLogger` |
| `simulate.py` | Test harness (no hardware needed) |

## Setup

```bash
cd rfid_direction_v1.0
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configure

Edit `config.yaml` — map each reader's real `DeviceMac` (or `DeviceSN`) to its
side and adjust timing:

```yaml
readers:
  "84D81B123456": Outside
  "84D81B654321": Inside
reader_id_field: "DeviceMac"
cooldown_seconds: 5
session_timeout_seconds: 5
```

## Run

```bash
python app.py
# or
uvicorn app:app --host 0.0.0.0 --port 8000
```

Readers POST to `http://<pi-ip>:8000/rfid`. Health check at `/health`.

Expected POST body (list of readings):

```json
[
  {
    "TagID": "300833B2DDD9014000000001",
    "TimeStamp": "2026-07-27T12:30:01.235",
    "AntennaNumber": "1",
    "DeviceMac": "84:D8:1B:12:34:56",
    "Rssi": "-52",
    "DeviceSN": "SN12345"
  }
]
```

## Test without hardware

```bash
python simulate.py            # runs the direction logic directly (offline)
python simulate.py --http     # POSTs to a running server on localhost:8000
```

## Deploy as a systemd service (Raspberry Pi)

```bash
sudo cp rfid-direction.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rfid-direction
journalctl -u rfid-direction -f
```

Adjust `User`, `WorkingDirectory` and the venv path in the unit file to match
your Pi.

## Logs

```
logs/app.log      general application log
logs/events.log   one block per ENTER/EXIT decision
logs/errors.log   warnings & errors
```

Example decision block:

```
[12:30:01.235]
EPC: 300833B2DDD9014000000001
First Reader: Outside
Second Reader: Inside
Elapsed: 820 ms
Decision: ENTER
```

## What V1.0 intentionally does NOT do

Approach/leave, reverse direction, doorway stall, tailgating, occupancy
counting, and a full per-tag state machine are out of scope. The event-driven,
loosely-coupled design is built so these drop in later as new subscribers or an
expanded direction engine.
