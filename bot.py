#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio
import copy
import json
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Optional, Tuple

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.mixers.soundfile_mixer import SoundfileMixer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    LLMRunFrame,
    LLMTextFrame,
    OutputTransportMessageFrame,
    TTSAudioRawFrame,
    TranscriptionFrame,
)
from pipecat.observers.loggers.transcription_log_observer import TranscriptionLogObserver
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import Frame, FrameDirection, FrameProcessor
from pipecat.processors.aggregators.llm_response import LLMUserContextAggregator
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.azure.tts import AzureTTSService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService, LiveOptions
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.tts_service import TTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.transcriptions.language import Language
from runner import configure

load_dotenv(override=True)

logger.remove(0)
log_level = os.getenv("BOT_LOG_LEVEL", "DEBUG")
logger.add(sys.stderr, level=log_level)

log_file_env = os.getenv("BOT_LOG_FILE")
timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
default_log_path = Path(f"logs/bot-{timestamp}.log")
log_file = Path(log_file_env) if log_file_env else default_log_path
log_file.parent.mkdir(parents=True, exist_ok=True)
logger.add(
    log_file,
    level=os.getenv("BOT_FILE_LOG_LEVEL", "INFO"),
    rotation="5 MB",
    retention=5,
    enqueue=True,
)

BACKGROUND_SOUND_FILE = "office-ambience-mono-16000.mp3"
TRANSLATION_TARGETS = [
    {
        "name": os.getenv("TARGET_LANGUAGE", "hindi"),
        "prompt": os.getenv(
            "TARGET_PROMPT",
            "You will be provided a sentence in English. Your task is to translate only the non-technical or everyday language into Hindi, while keeping all technical, domain-specific, or specialized terms in English. Do not translate jargon, proper nouns, system or product names, scientific/engineering/business terminology, or any field-specific phrases. Translate only the general descriptive text and natural language around those terms.",
        ),
        "voice_env": os.getenv("TARGET_VOICE_ENV", "AZURE_TTS_VOICE_HINDI"),
        "default_voice": os.getenv("TARGET_DEFAULT_VOICE", "hi-IN-SwaraNeural"),
        "cartesia_voice_env": os.getenv("TARGET_CARTESIA_VOICE_ENV", "CARTESIA_TTS_VOICE_HINDI"),
        "cartesia_default_voice": os.getenv("TARGET_CARTESIA_DEFAULT_VOICE", "hindi-default"),
        "language": Language[os.getenv("TARGET_LANGUAGE_CODE", "HI_IN")],
    }
]


class TranslationTranscriptEmitter(FrameProcessor):
    """Injects translation text into transport messages for downstream clients."""

    def __init__(self, *, language: str):
        super().__init__(name=f"{language}-transcript-emitter")
        self._language = language

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if direction is FrameDirection.DOWNSTREAM and isinstance(frame, LLMTextFrame):
            payload = json.dumps(
                {
                    "type": "translation-transcript",
                    "language": self._language,
                    "text": frame.text,
                    "timestamp": time.time(),
                }
            )
            await self.push_frame(OutputTransportMessageFrame(message=payload), direction)

        await self.push_frame(frame, direction)


@dataclass
class TranscriptChunk:
    """Represents a single STT chunk with timestamp metadata."""

    id: str
    text: str
    timestamp: float


class TranscriptionChunkBuffer(FrameProcessor):
    """Captures STT output in chronological order and tags frames with chunk metadata."""

    def __init__(self, history_size: int = 200):
        super().__init__(name="transcription-chunk-buffer")
        self._history: Deque[TranscriptChunk] = deque(maxlen=history_size)
        self._counter = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if direction is FrameDirection.DOWNSTREAM and isinstance(frame, LLMTextFrame):
            self._counter += 1
            chunk_id = f"chunk-{self._counter}"
            timestamp = time.time()
            frame.metadata["chunk_id"] = chunk_id
            frame.metadata["chunk_timestamp"] = timestamp
            self._history.append(TranscriptChunk(id=chunk_id, text=frame.text, timestamp=timestamp))
            logger.info("[stt] chunk={} timestamp={:.3f} text={}", chunk_id, timestamp, frame.text)

        await self.push_frame(frame, direction)


class SequentialTranslationQueue(FrameProcessor):
    """Guarantees translations feed the TTS stage one chunk at a time."""

    def __init__(self, *, language: str):
        super().__init__(name=f"{language}-translation-queue")
        self._language = language
        self._queue: asyncio.Queue[Tuple[LLMTextFrame, FrameDirection]] = asyncio.Queue()
        self._drain_task: Optional[asyncio.Task] = None
        self._drain_lock = asyncio.Lock()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if direction is FrameDirection.DOWNSTREAM and isinstance(frame, LLMTextFrame):
            await self._queue.put((frame, direction))
            await self._ensure_drain()
        else:
            await self.push_frame(frame, direction)

    async def _ensure_drain(self):
        if self._drain_task and not self._drain_task.done():
            return
        self._drain_task = asyncio.create_task(self._drain_queue())

    async def _drain_queue(self):
        async with self._drain_lock:
            while not self._queue.empty():
                frame, direction = await self._queue.get()
                chunk_id = frame.metadata.get("chunk_id", "unknown")
                logger.info(
                    "[translation] language={} chunk={} text={}",
                    self._language,
                    chunk_id,
                    frame.text,
                )
                try:
                    await self.push_frame(frame, direction)
                    logger.info(
                        "[translation-output] language={} chunk={} text={}",
                        self._language,
                        chunk_id,
                        frame.text,
                    )
                    logger.info(
                        "[translation] language={} chunk={} status=delivered",
                        self._language,
                        chunk_id,
                    )
                finally:
                    self._queue.task_done()


class TranscriptionStreamAdapter(FrameProcessor):
    """Logs interim STT results and emits final transcripts."""

    def __init__(self):
        super().__init__(name="transcription-stream-adapter")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InterimTranscriptionFrame):
            logger.info("[stt-interim] text={} timestamp={} language={}", frame.text, frame.timestamp, frame.language)
            return

        if isinstance(frame, TranscriptionFrame):
            logger.info("[stt-final] text={} timestamp={} language={}", frame.text, frame.timestamp, frame.language)
            frame.metadata = dict(frame.metadata or {})
            frame.metadata.update(
                {
                    "chunk_timestamp": frame.timestamp,
                    "chunk_language": frame.language.value if frame.language else None,
                    "chunk_user": frame.user_id,
                }
            )
            await self.push_frame(frame, direction)
            return

        await self.push_frame(frame, direction)


class DirectTranslationProcessor(FrameProcessor):
    """Calls OpenAI per chunk to produce the translated text."""

    def __init__(self, *, llm: OpenAILLMService, system_prompt: str, target_language: str):
        super().__init__(name=f"{target_language}-translation-processor")
        self._llm = llm
        self._system_prompt = system_prompt
        self._target_language = target_language

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if not isinstance(frame, TranscriptionFrame):
            await self.push_frame(frame, direction)
            return

        text = frame.text.strip()
        if not text:
            return

        chunk_id = frame.metadata.get("chunk_id", "unknown")
        logger.info("[llm-request] chunk={} text={}", chunk_id, text)

        context = OpenAILLMContext(
            [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": text},
            ]
        )
        translation = await self._llm.run_inference(context)
        translation = (translation or "").strip()
        if not translation:
            logger.warning("No translation received for chunk %s; falling back to source text.", chunk_id)
            translation = text

        logger.info("[translation-output] language={} chunk={} text={}", self._target_language, chunk_id, translation)

        translated_frame = LLMTextFrame(text=translation)
        translated_frame.metadata.update(frame.metadata)
        await self.push_frame(translated_frame, direction)


class TTSAudioLogger(FrameProcessor):
    """Logs every audio buffer generated by the TTS engine for traceability."""

    def __init__(self, *, language: str):
        super().__init__(name=f"{language}-tts-logger")
        self._language = language

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if direction is FrameDirection.DOWNSTREAM and isinstance(frame, TTSAudioRawFrame):
            chunk_id = frame.metadata.get("chunk_id", "unknown")
            logger.info(
                "[tts] language={} chunk={} pts={} bytes={}",
                self._language,
                chunk_id,
                frame.pts,
                len(frame.audio) if hasattr(frame, "audio") and frame.audio else 0,
            )

        await self.push_frame(frame, direction)


def _create_llm_service() -> OpenAILLMService:
    api_key = os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing LiteLLM/OpenAI credentials. Please set LITELLM_API_KEY or OPENAI_API_KEY."
        )

    base_url = os.getenv("LITELLM_API_BASE") or os.getenv("OPENAI_BASE_URL")
    model = os.getenv("LITELLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"

    return OpenAILLMService(api_key=api_key, base_url=base_url, model=model)


def _create_azure_tts(
    *,
    voice: str,
    language: Language,
    destination: str,
) -> AzureTTSService:
    api_key = os.getenv("AZURE_SPEECH_KEY")
    region = os.getenv("AZURE_SPEECH_REGION")
    if not api_key or not region:
        raise RuntimeError(
            "Missing Azure Speech credentials. Please set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION."
        )

    return AzureTTSService(
        api_key=api_key,
        region=region,
        voice=voice,
        sample_rate=16000,
        transport_destination=destination,
        params=AzureTTSService.InputParams(language=language),
    )


def _create_cartesia_tts(
    *,
    voice_id: str,
    language: Language,
    destination: str,
) -> CartesiaTTSService:
    api_key = os.getenv("CARTESIA_API_KEY")
    if not api_key:
        raise RuntimeError("Missing Cartesia credentials. Please set CARTESIA_API_KEY.")

    model = os.getenv("CARTESIA_TTS_MODEL", "sonic-3")
    cartesia_version = os.getenv("CARTESIA_API_VERSION", "2025-04-16")
    ws_url = os.getenv("CARTESIA_TTS_URL", "wss://api.cartesia.ai/tts/websocket")
    sample_rate = os.getenv("CARTESIA_SAMPLE_RATE")
    resolved_sample_rate = int(sample_rate) if sample_rate else 16000

    return CartesiaTTSService(
        api_key=api_key,
        voice_id=voice_id,
        model=model,
        cartesia_version=cartesia_version,
        url=ws_url,
        sample_rate=resolved_sample_rate,
        transport_destination=destination,
        params=CartesiaTTSService.InputParams(language=language),
    )


def _resolve_voice_id(target: dict, provider: str) -> str:
    if provider == "cartesia":
        env_name = target.get("cartesia_voice_env")
        voice = (os.getenv(env_name) if env_name else None) or os.getenv("CARTESIA_DEFAULT_VOICE") or target.get("cartesia_default_voice")
    else:
        env_name = target.get("voice_env")
        voice = (os.getenv(env_name) if env_name else None) or target.get("default_voice")

    if not voice:
        raise RuntimeError(f"Missing voice configuration for {target['name']} using provider '{provider}'.")
    return voice


def _create_tts_service(
    *,
    provider: str,
    voice_id: str,
    language: Language,
    destination: str,
) -> TTSService:
    if provider == "cartesia":
        return _create_cartesia_tts(voice_id=voice_id, language=language, destination=destination)
    return _create_azure_tts(voice=voice_id, language=language, destination=destination)


async def main():
    async with aiohttp.ClientSession() as session:
        (room_url, token) = await configure(session)

        target = TRANSLATION_TARGETS[0]
        audio_destinations = [target["name"]]
        audio_out_mixer = {
            target["name"]: SoundfileMixer(
                sound_files={"office": BACKGROUND_SOUND_FILE}, default_sound="office"
            )
        }

        transport = DailyTransport(
            room_url,
            token,
            "Multi translation bot",
            DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                audio_out_mixer=audio_out_mixer,
                audio_out_destinations=audio_destinations,
                video_in_enabled=False,
                video_out_enabled=False,
                camera_out_enabled=False,
                microphone_out_enabled=False,  # Disable since we just use custom tracks
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )

        stt = DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            live_options=LiveOptions(interim_results=True, vad_events=False),
        )
        transcription_adapter = TranscriptionStreamAdapter()
        tts_provider = os.getenv("TTS_PROVIDER", "azure").strip().lower()
        if tts_provider not in ("azure", "cartesia"):
            raise RuntimeError(
                f"Unsupported TTS_PROVIDER '{tts_provider}'. Expected 'azure' or 'cartesia'."
            )

        chunk_buffer = TranscriptionChunkBuffer()
        target = TRANSLATION_TARGETS[0]
        llm_service = _create_llm_service()
        translator = DirectTranslationProcessor(
            llm=llm_service,
            system_prompt=target["prompt"],
            target_language=target["name"],
        )
        voice_id = _resolve_voice_id(target, tts_provider)
        tts_service = _create_tts_service(
            provider=tts_provider,
            voice_id=voice_id,
            language=target["language"],
            destination=target["name"],
        )

        translation_branch = [
            translator,
            TranslationTranscriptEmitter(language=target["name"]),
            SequentialTranslationQueue(language=target["name"]),
            tts_service,
            TTSAudioLogger(language=target["name"]),
        ]

        pipeline = Pipeline(
            [
                transport.input(),  # Transport user input
                stt,
                transcription_adapter,
                chunk_buffer,
                ParallelPipeline(translation_branch),
                transport.output(),  # Transport bot output
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=16000,
                audio_out_sample_rate=16000,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            observers=[TranscriptionLogObserver()],
        )

        runner = PipelineRunner()
        await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
