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
TARGET_LANG = os.getenv("TARGET_LANG", "hi-IN")
TTS_VOICE = os.getenv("TTS_VOICE", "hi-IN-KavyaNeural")
VOICE_MAP = {TARGET_LANG: TTS_VOICE}
WS_INGEST_PATH = os.getenv("WS_INGEST_PATH", "/ingest")
WS_OUT_PATH = os.getenv("WS_OUT_PATH", "/out")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
BYTES_PER_SAMPLE = 2
