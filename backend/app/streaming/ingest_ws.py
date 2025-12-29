import json

from fastapi import APIRouter, WebSocket

from app.orchestration.pipeline import handle_session

router = APIRouter()

@router.websocket("/ingest")
async def ingest(ws: WebSocket):
    await ws.accept()
    meta = await ws.receive_text()
    await handle_session(ws, meta)
