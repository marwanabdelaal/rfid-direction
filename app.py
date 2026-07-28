from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request

app = FastAPI(title="Raw RFID Listener")


@app.post("/rfid")
async def rfid(request: Request):
    data = await request.json()
    for tag in data:
        print(tag["epc"])
    return {"status":"ok"}



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
