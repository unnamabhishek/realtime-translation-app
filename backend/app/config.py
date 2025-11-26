import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "")
AZURE_TRANSLATOR_KEY = os.getenv("AZURE_TRANSLATOR_KEY", "")
AZURE_TRANSLATOR_ENDPOINT = os.getenv("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com")
AZURE_TRANSLATOR_REGION = os.getenv("AZURE_TRANSLATOR_REGION", "")
DEFAULT_SOURCE_LANG = os.getenv("SOURCE_LANG", "en-US")
TARGET_LANGS = [lang for lang in os.getenv("TARGET_LANGS", "hi-IN").split(",") if lang]
TTS_VOICE_HI = os.getenv("TTS_VOICE_HI", "hi-IN-KavyaNeural")
TTS_VOICE_MR = os.getenv("TTS_VOICE_MR", "mr-IN-AarohiNeural")
VOICE_MAP = {"hi-IN": TTS_VOICE_HI, "mr-IN": TTS_VOICE_MR}
WS_INGEST_PATH = os.getenv("WS_INGEST_PATH", "/ingest")
WS_OUT_PATH = os.getenv("WS_OUT_PATH", "/out")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
BYTES_PER_SAMPLE = 2