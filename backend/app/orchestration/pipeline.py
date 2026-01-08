import asyncio
import io
import json
import logging
import time
import uuid
import wave
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
    LOCAL_TTS_PLAYBACK,
    SAMPLE_RATE,
    SEND_WS_AUDIO,
    TARGET_LANG,
    TTS_OUTPUT_CHANNELS,
    TTS_OUTPUT_DEVICE,
    TTS_OUTPUT_SAMPLE_RATE,
    TTS_RATE,
    VOICE_MAP,
)
from app.nlp.segmenter import should_cut_segment
from app.nlp.translator import translate_texts
from app.streaming.out_ws import SUBS
from app.stt.azure_stt import make_speech_recognizer
import numpy as np
import sounddevice as sd
from app.tts.azure_tts import stream_pcm

logger = logging.getLogger("pipeline")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

def _ensure_session_logger(session_id: str) -> None:
    log_dir = Path(__file__).resolve().parents[3] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"pipeline-{session_id}.log"
    if any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_file for handler in logger.handlers):
        return
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
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
MAX_SEGMENT_CHARS = 20
MAX_SEGMENT_HARD_CHARS = 40
_local_stream = None
_local_stream_rate = None
_local_stream_channels = None

async def handle_session(ws: WebSocket, meta_json: str) -> None:
    meta = json.loads(meta_json)
    session_id = meta.get("session_id") or str(uuid.uuid4())
    _ensure_session_logger(session_id)
    source_lang = meta.get("lang_src", DEFAULT_SOURCE_LANG)
    target = meta.get("target") or (meta.get("targets", [])[:1] or [TARGET_LANG])[0]
    logger.info("session start id=%s src=%s target=%s", session_id, source_lang, target)
    recognizer, audio_stream = make_speech_recognizer(AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, source_lang, load_glossary_terms())
    buffer_text = ""
    silence_ms = 0
    last_loop_ts = time.perf_counter()
    last_recognized_ts = None
    result_queue: asyncio.Queue[str] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_recognized(evt):
        text = evt.result.text.strip()
        if text:
            loop.call_soon_threadsafe(result_queue.put_nowait, text)

    recognizer.recognized.connect(on_recognized)
    recognizer.start_continuous_recognition()

    while True:
        try:
            message = await asyncio.wait_for(ws.receive(), timeout=0.2)
        except asyncio.TimeoutError:
            message = None
        if message and "bytes" in message:
            payload = message["bytes"]
            audio_stream.write(payload)
            frame_ms = int(len(payload) / (BYTES_PER_SAMPLE * SAMPLE_RATE) * 1000)
            silence_ms = max(0, silence_ms - frame_ms)
        elif message and "text" in message and message["text"] == "EOF":
            break

        while not result_queue.empty():
            text = await result_queue.get()
            buffer_text = f"{buffer_text} {text}".strip() if buffer_text else text
            logger.info("stt recognized session=%s text=%s", session_id, text)
            last_recognized_ts = time.perf_counter()

        now = time.perf_counter()
        elapsed_ms = int((now - last_loop_ts) * 1000)
        last_loop_ts = now
        silence_ms = min(2000, silence_ms + elapsed_ms)

        idle_ms = int((time.perf_counter() - last_recognized_ts) * 1000) if last_recognized_ts else 0
        should_cut = should_cut_segment(buffer_text, silence_ms) or (buffer_text and idle_ms >= 2000)
        over_soft_limit = len(buffer_text) >= MAX_SEGMENT_CHARS and buffer_text.strip().endswith((".", "?", "!", "।", "॥", "…"))
        over_hard_limit = len(buffer_text) >= MAX_SEGMENT_HARD_CHARS

        if buffer_text and (should_cut or over_soft_limit or over_hard_limit):
            chunk_id = f"{session_id}-{int(time.time()*1000)}"
            await process_segment(session_id, chunk_id, buffer_text, target)
            buffer_text = ""
            silence_ms = 0

    recognizer.stop_continuous_recognition()


async def process_segment(session_id: str, chunk_id: str, text: str, target: str) -> None:
    terms = load_glossary_terms()
    logger.info("segment start session=%s chunk=%s text=%s", session_id, chunk_id, text)
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
    global _local_stream, _local_stream_rate, _local_stream_channels
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
            send_ts = time.time()
            chunk_meta = json.dumps(
                {
                    "session_id": session_id,
                    "chunk_id": chunk_id,
                    "target": target,
                    "text": translated,
                    "timestamp": send_ts,
                    "duration_sec": 0.0,
                }
            )
            alive = []
            if SEND_WS_AUDIO:
                clients = SUBS.get(session_id, {}).get(target, [])
                for client in clients:
                    try:
                        await client.send_text(chunk_meta)
                        alive.append(client)
                    except Exception as exc:
                        logger.warning("drop closed client session=%s target=%s error=%s", session_id, target, exc)
                SUBS.get(session_id, {}).update({target: alive})

            pcm_chunks = []
            local_play_start = None
            async for pcm in stream_pcm(translated, AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, voice, TTS_OUTPUT_SAMPLE_RATE, TTS_RATE):
                pcm_chunks.append(pcm)
                if LOCAL_TTS_PLAYBACK:
                    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
                    if TTS_OUTPUT_CHANNELS == 2:
                        audio = np.repeat(audio[:, None], 2, axis=1)
                    if _local_stream is None or _local_stream_rate != TTS_OUTPUT_SAMPLE_RATE or _local_stream_channels != TTS_OUTPUT_CHANNELS:
                        if _local_stream is not None:
                            _local_stream.stop()
                            _local_stream.close()
                        _local_stream_rate = TTS_OUTPUT_SAMPLE_RATE
                        _local_stream_channels = TTS_OUTPUT_CHANNELS
                        device = TTS_OUTPUT_DEVICE if TTS_OUTPUT_DEVICE else None
                        _local_stream = sd.OutputStream(device=device, channels=TTS_OUTPUT_CHANNELS, samplerate=TTS_OUTPUT_SAMPLE_RATE, dtype="float32")
                        _local_stream.start()
                    if local_play_start is None:
                        local_play_start = time.time()
                        logger.info("local playback start session=%s chunk=%s target=%s ts=%.3f", session_id, chunk_id, target, local_play_start)
                    await asyncio.to_thread(_local_stream.write, audio)

            pcm_bytes = b"".join(pcm_chunks)
            duration_sec = len(pcm_bytes) / float(TTS_OUTPUT_SAMPLE_RATE * BYTES_PER_SAMPLE) if pcm_bytes else 0.0
            _tts_expected_end[target] = send_ts + duration_sec
            _tts_last_duration[target] = duration_sec

            wav_bytes = b""
            if pcm_bytes:
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(BYTES_PER_SAMPLE)
                    wav.setframerate(TTS_OUTPUT_SAMPLE_RATE)
                    wav.writeframes(pcm_bytes)
                wav_bytes = buffer.getvalue()

            logger.info(
                "tts done session=%s chunk=%s target=%s bytes=%s duration=%.2fs",
                session_id,
                chunk_id,
                target,
                len(pcm_bytes),
                duration_sec,
            )
            if local_play_start is not None:
                logger.info("local playback end session=%s chunk=%s target=%s ts=%.3f duration=%.2fs", session_id, chunk_id, target, time.time(), duration_sec)

            if SEND_WS_AUDIO and alive and wav_bytes:
                for client in alive:
                    try:
                        await client.send_bytes(wav_bytes)
                    except Exception as exc:
                        logger.warning("drop closed client session=%s target=%s error=%s", session_id, target, exc)
                SUBS.get(session_id, {}).update({target: alive})
            elif SEND_WS_AUDIO and not alive:
                logger.info("no active clients session=%s target=%s; audio dropped", session_id, target)

        queue.task_done()


def load_glossary_terms() -> list[str]:
    path = Path(__file__).parent.parent / "glossary" / "do_not_translate.tsv"
    if not path.exists():
        return []
    return [line.split("\t")[0].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
