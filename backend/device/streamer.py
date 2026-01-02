import asyncio, json, os, uuid, subprocess, websockets
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

MP3_PATH = os.getenv("MP3_PATH", "/Users/abhishekunnam/Projects/realtime-translation-app/audios/Keynote.mp3")
SESSION = os.getenv("SESSION_ID", "07ef71fe-5249-410e-a6e2-873777fb41cf")
WS_URL = os.getenv("BACKEND_URL", "ws://localhost:8080/ingest")
SAMPLE_RATE = 16000
FRAME_MS = 20
BYTES_PER_FRAME = int(SAMPLE_RATE * FRAME_MS / 1000 * 2)  # PCM16 mono
TARGET = os.getenv("TARGET_LANG", "hi-IN")
SOURCE = os.getenv("SOURCE_LANG", "en-US")

async def main():
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"session_id": SESSION, "lang_src": SOURCE, "target": TARGET}))
        proc = subprocess.Popen(
            ["ffmpeg", "-i", MP3_PATH, "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        while True:
            chunk = proc.stdout.read(BYTES_PER_FRAME)
            if not chunk:
                break
            await ws.send(chunk)
            await asyncio.sleep(FRAME_MS / 1000)
        await ws.send("EOF")
    proc.wait()

asyncio.run(main())
