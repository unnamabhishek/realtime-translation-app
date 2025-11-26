from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import SAMPLE_RATE

router = APIRouter()
SUBS: Dict[str, Dict[str, List[WebSocket]]] = {}


@router.websocket("/out/{session_id}/{target}")
async def out(ws: WebSocket, session_id: str, target: str):
    await ws.accept()
    await ws.send_text(f'{{"session_id":"{session_id}","target":"{target}","sample_rate":{SAMPLE_RATE}}}')
    SUBS.setdefault(session_id, {}).setdefault(target, []).append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        sessions = SUBS.get(session_id, {})
        if target in sessions:
            sessions[target] = [client for client in sessions[target] if client is not ws]
            if not sessions[target]:
                sessions.pop(target)
        if not sessions:
            SUBS.pop(session_id, None)
