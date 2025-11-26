from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment before importing modules that read it.
BASE_DIR = Path(__file__)
load_dotenv(BASE_DIR.parent.parent / ".env")

from app.streaming.ingest_ws import router as ingest_router  # noqa: E402
from app.streaming.out_ws import router as out_router  # noqa: E402

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ingest_router)
app.include_router(out_router)
