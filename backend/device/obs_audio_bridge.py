import asyncio
import io
import json
import os
import time
import wave
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
import sounddevice as sd
import websockets

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

SESSION_ID = os.getenv("SESSION_ID", "07ef71fe-5249-410e-a6e2-873777fb41cf")
TARGET = os.getenv("TARGET_LANG", "hi-IN")
BACKEND_URL = os.getenv("BACKEND_URL", "ws://localhost:8080")
LOG_EVERY_CHUNKS = int(os.getenv("LOG_EVERY_CHUNKS", "1"))
OUTPUT_DEVICE = os.getenv("OUTPUT_DEVICE", "BlackHole 64ch")
LOG_DIR = Path(os.getenv("LOG_DIR", "/Users/abhishekunnam/Projects/realtime-translation-app/logs"))
OBS_LOG_PATH = LOG_DIR / f"obs-{SESSION_ID}.log"

_stream = None
_stream_rate = None
_stream_lock = asyncio.Lock()
_pending_meta = None

def _append_log(line: str) -> None:
    OBS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OBS_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")

def _ensure_stream(sample_rate: int) -> None:
    global _stream, _stream_rate
    if _stream is None or _stream_rate != sample_rate:
        if _stream is not None:
            _stream.stop()
            _stream.close()
        _stream_rate = sample_rate
        _stream = sd.OutputStream(
            device=OUTPUT_DEVICE,
            channels=2,
            samplerate=_stream_rate,
            dtype="float32",
        )
        _stream.start()

async def _listen_target() -> None:
    ws_url = f"{BACKEND_URL}/out/{SESSION_ID}/{TARGET}"
    chunk_count = 0
    async with websockets.connect(ws_url, max_size=None) as ws:
        while True:
            message = await ws.recv()
            if isinstance(message, str):
                meta = json.loads(message)
                if meta.get("sample_rate"):
                    continue
                _pending_meta = meta
                continue
            with wave.open(io.BytesIO(message), "rb") as wav:
                frames = wav.readframes(wav.getnframes())
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                rate = wav.getframerate()
            chunk_count += 1
            if LOG_EVERY_CHUNKS and chunk_count % LOG_EVERY_CHUNKS == 0:
                now = time.strftime("%H:%M:%S")
                print(f"[{now}] target={TARGET} chunk={chunk_count} samples={len(audio)} rate={rate}")
            stereo = np.repeat(audio[:, None], 2, axis=1)
            async with _stream_lock:
                _ensure_stream(rate)
                started_at = time.strftime("%H:%M:%S")
                if _pending_meta:
                    start_line = f"[{started_at}] start chunk={chunk_count} text={_pending_meta.get('text','')} target={TARGET}"
                else:
                    start_line = f"[{started_at}] start chunk={chunk_count} target={TARGET}"
                print(start_line)
                await asyncio.to_thread(_append_log, start_line)
                write_start = time.perf_counter()
                await asyncio.to_thread(_stream.write, stereo)
                write_elapsed = time.perf_counter() - write_start
            chunk_duration = len(audio) / float(rate)
            _pending_meta = None

async def run() -> None:
    default_output = sd.default.device[1]
    output_info = sd.query_devices(default_output) if default_output is not None else None
    print(f"default output device: {output_info['name'] if output_info else default_output}")
    await _listen_target()

if __name__ == "__main__":
    asyncio.run(run())
