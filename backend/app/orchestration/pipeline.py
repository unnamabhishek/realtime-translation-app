import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict
from fastapi import WebSocket

from app.config import (
    AZURE_SPEECH_KEY,
    AZURE_SPEECH_REGION,
    AZURE_TRANSLATOR_ENDPOINT,
    AZURE_TRANSLATOR_KEY,
    AZURE_TRANSLATOR_REGION,
    BYTES_PER_SAMPLE,
    DEFAULT_SOURCE_LANG,
    SAMPLE_RATE,
    TARGET_LANGS,
    VOICE_MAP,
)
from app.nlp.segmenter import should_cut_segment
from app.nlp.translator import translate_texts
from app.streaming.out_ws import SUBS
from app.stt.azure_stt import make_speech_recognizer
from app.tts.azure_tts import synth_wav

logger = logging.getLogger("pipeline")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    log_dir = Path(__file__).resolve().parents[3] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"pipeline-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# Per-target TTS sequencing state
_tts_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_tts_expected_end: dict[str, float] = defaultdict(float)
_tts_queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
_tts_tasks: Dict[str, asyncio.Task] = {}
_tts_last_duration: Dict[str, float] = defaultdict(float)
TTS_LEAD_TIME_SECONDS = 1.5  # max lead time before previous ends
MAX_SEGMENT_CHARS = 400
MAX_SEGMENT_HARD_CHARS = 600

async def handle_session(ws: WebSocket, meta_json: str) -> None:
    meta = json.loads(meta_json)
    session_id = meta.get("session_id") or str(uuid.uuid4())
    source_lang = meta.get("lang_src", DEFAULT_SOURCE_LANG)
    targets = meta.get("targets", TARGET_LANGS)
    logger.info("session start id=%s src=%s targets=%s", session_id, source_lang, targets)
    recognizer, audio_stream = make_speech_recognizer(AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, source_lang, load_glossary_terms())
    buffer_text = ""
    silence_ms = 0
    last_audio_ts = time.perf_counter()
    result_queue: asyncio.Queue[str] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_recognized(evt):
        text = evt.result.text.strip()
        if text:
            loop.call_soon_threadsafe(result_queue.put_nowait, text)

    recognizer.recognized.connect(on_recognized)
    recognizer.start_continuous_recognition()

    while True:
        message = await ws.receive()
        if "bytes" in message:
            payload = message["bytes"]
            audio_stream.write(payload)
            frame_ms = int(len(payload) / (BYTES_PER_SAMPLE * SAMPLE_RATE) * 1000)
            silence_ms = max(0, silence_ms - frame_ms)
            last_audio_ts = time.perf_counter()
        elif "text" in message and message["text"] == "EOF":
            break

        while not result_queue.empty():
            text = await result_queue.get()
            buffer_text = f"{buffer_text} {text}".strip() if buffer_text else text
            logger.info("stt recognized session=%s text=%s", session_id, text)

        elapsed_ms = int((time.perf_counter() - last_audio_ts) * 1000)
        silence_ms = min(2000, silence_ms + elapsed_ms)

        should_cut = should_cut_segment(buffer_text, silence_ms)
        over_soft_limit = len(buffer_text) >= MAX_SEGMENT_CHARS and buffer_text.strip().endswith((".", "?", "!", "।", "॥", "…"))
        over_hard_limit = len(buffer_text) >= MAX_SEGMENT_HARD_CHARS

        if buffer_text and (should_cut or over_soft_limit or over_hard_limit):
            chunk_id = f"{session_id}-{int(time.time()*1000)}"
            await process_segment(session_id, chunk_id, buffer_text, targets)
            buffer_text = ""
            silence_ms = 0

    recognizer.stop_continuous_recognition()


async def process_segment(session_id: str, chunk_id: str, text: str, targets: list[str]) -> None:
    terms = load_glossary_terms()
    logger.info("segment start session=%s chunk=%s text=%s", session_id, chunk_id, text)
    for target in targets:
        translated_list = translate_texts([text], target, AZURE_TRANSLATOR_KEY, AZURE_TRANSLATOR_ENDPOINT, AZURE_TRANSLATOR_REGION, terms)
        translated = translated_list[0] if translated_list else ""
        logger.info("translation session=%s chunk=%s target=%s text=%s", session_id, chunk_id, target, translated)
        await _enqueue_tts(session_id, chunk_id, translated, target)
    logger.info("segment done session=%s chunk=%s", session_id, chunk_id)


async def _enqueue_tts(session_id: str, chunk_id: str, translated_text: str, target: str) -> None:
    queue = _tts_queues[target]
    await queue.put((session_id, chunk_id, translated_text))
    if target not in _tts_tasks or _tts_tasks[target].done():
        _tts_tasks[target] = asyncio.create_task(_tts_worker(target))


async def _tts_worker(target: str) -> None:
    lock = _tts_locks[target]
    queue = _tts_queues[target]
    while True:
        try:
            session_id, chunk_id, translated = await queue.get()
        except asyncio.CancelledError:
            break

        async with lock:
            now = time.time()
            expected_end = _tts_expected_end.get(target, 0.0)
            lead_time = min(_tts_last_duration.get(target, 0.0), TTS_LEAD_TIME_SECONDS)
            wait_for = max(0.0, expected_end - lead_time - now)
            if wait_for > 0:
                logger.info("tts wait session=%s chunk=%s target=%s wait=%.2fs", session_id, chunk_id, target, wait_for)
                await asyncio.sleep(wait_for)

            voice = VOICE_MAP.get(target, VOICE_MAP.get("hi-IN", ""))
            logger.info("tts start session=%s chunk=%s target=%s voice=%s", session_id, chunk_id, target, voice)
            synth_start = time.time()
            audio_bytes = await asyncio.to_thread(synth_wav, translated, AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, voice)
            synth_elapsed = time.time() - synth_start
            duration_sec = len(audio_bytes) / float(SAMPLE_RATE * BYTES_PER_SAMPLE) if audio_bytes else 0.0
            send_ts = time.time()
            _tts_expected_end[target] = send_ts + duration_sec
            logger.info(
                "tts done session=%s chunk=%s target=%s bytes=%s synth_elapsed=%.2fs duration=%.2fs",
                session_id,
                chunk_id,
                target,
                len(audio_bytes),
                synth_elapsed,
                duration_sec,
            )
            _tts_last_duration[target] = duration_sec

            chunk_meta = json.dumps(
                {
                    "session_id": session_id,
                    "chunk_id": chunk_id,
                    "target": target,
                    "text": translated,
                    "timestamp": send_ts,
                    "duration_sec": duration_sec,
                }
            )
            clients = SUBS.get(session_id, {}).get(target, [])
            alive = []
            for client in clients:
                try:
                    await client.send_text(chunk_meta)
                    await client.send_bytes(audio_bytes)
                    alive.append(client)
                except Exception as exc:
                    logger.warning("drop closed client session=%s target=%s error=%s", session_id, target, exc)
            SUBS.get(session_id, {}).update({target: alive})
            if not alive:
                logger.info("no active clients session=%s target=%s; audio dropped", session_id, target)

        queue.task_done()


def load_glossary_terms() -> list[str]:
    path = Path(__file__).parent.parent / "glossary" / "do_not_translate.tsv"
    if not path.exists():
        return []
    return [line.split("\t")[0].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
