import asyncio
import json
import uuid

import numpy as np
import sounddevice as sd
import websockets

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 320  # 20ms
SESSION_ID = str(uuid.uuid4())


async def run() -> None:
    async with websockets.connect("ws://localhost:8080/ingest") as ws:
        await ws.send(json.dumps({"session_id": SESSION_ID, "lang_src": "en-US", "targets": ["hi-IN"]}))

        def callback(indata, frames, time_info, status):
            pcm = (indata.copy() * 32767).astype("<i2").tobytes()
            asyncio.run(ws.send(pcm))

        with sd.InputStream(channels=CHANNELS, samplerate=SAMPLE_RATE, blocksize=CHUNK, dtype="float32", callback=callback):
            await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(run())
