import asyncio
import io
import json
import time
import wave
import numpy as np
import sounddevice as sd
import websockets

SESSION_ID = "07ef71fe-5249-410e-a6e2-873777fb41cf"
TARGET = "hi-IN"
BACKEND_URL = "ws://localhost:8080"
LOG_EVERY_CHUNKS = 1

def _play_audio(samples: np.ndarray, sample_rate: int) -> None:
    sd.play(samples, sample_rate)
    sd.wait()

async def run() -> None:
    default_output = sd.default.device[1]
    output_info = sd.query_devices(default_output) if default_output is not None else None
    print(f"default output device: {output_info['name'] if output_info else default_output}")
    ws_url = f"{BACKEND_URL}/out/{SESSION_ID}/{TARGET}"
    async with websockets.connect(ws_url, max_size=None) as ws:
        chunk_count = 0
        while True:
            message = await ws.recv()
            if isinstance(message, str):
                meta = json.loads(message)
                if meta.get("sample_rate"):
                    continue
                continue
            with wave.open(io.BytesIO(message), "rb") as wav:
                frames = wav.readframes(wav.getnframes())
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                sample_rate = wav.getframerate()
            chunk_count += 1
            if LOG_EVERY_CHUNKS and chunk_count % LOG_EVERY_CHUNKS == 0:
                now = time.strftime("%H:%M:%S")
                print(f"[{now}] audio chunk={chunk_count} samples={len(audio)} rate={sample_rate}")
            await asyncio.to_thread(_play_audio, audio, sample_rate)

if __name__ == "__main__":
    asyncio.run(run())
