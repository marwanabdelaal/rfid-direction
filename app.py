"""Simplest possible HTTP listener for the UHF readers.

Purpose: just receive POSTs from the readers and print the RAW body, so you can
see exactly what a Hopeland reader sends before building any parsing logic.

Run:
    pip install fastapi uvicorn
    python raw_listener.py

Point the readers at:
    POST http://<this-pi-ip>:8000/rfid
"""
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request

app = FastAPI(title="Raw RFID Listener")


@app.post("/rfid")
async def rfid(request: Request):
    raw = await request.body()
    print("=" * 60)
    print(f"POST /rfid  @ {datetime.now().isoformat(timespec='milliseconds')}")
    print(f"From: {request.client.host if request.client else 'unknown'}")
    print(f"Content-Type: {request.headers.get('content-type')}")
    print(f"Bytes: {len(raw)}")
    print("-" * 60)
    print(raw.decode(errors="replace"))
    print("=" * 60, flush=True)
    return {"status": "ok", "bytes": len(raw)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
