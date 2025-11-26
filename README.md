# Realtime Translation (No Daily)

Low-latency mic → backend (WS) → STT → translate → TTS → web playback without Daily/meeting infra.

## Layout
- `backend/`: FastAPI app with `/ingest` (PCM16 WS in) and `/out/{session}/{target}` (audio/text WS out).
- `backend/app/stt|nlp|tts|streaming|orchestration`: Azure STT/TTS, glossary-backed translation, segmenter, pipelines.
- `backend/device/`: Mic → WebSocket capture client.
- `backend/web/`: Simple React/Next starter for playback.
- `backend/ops/`: Docker compose for the backend.

## Quickstart
1) `cp backend/.env.example backend/.env` and fill Azure Speech + Translator keys.
2) Backend: `cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8080`.
3) Device sender: `cd backend/device && pip install -r requirements.txt && python mic_client.py`.
4) Web listener: `cd backend/web && npm install && npm run dev`, then open `http://localhost:3000` and enter the session id printed by the mic client.

## Protocols
- Ingest WS: first message JSON `{"session_id":"<uuid>","lang_src":"en-US","targets":["hi-IN"]}`, subsequent frames raw PCM16 mono 16k.
- Out WS: server sends JSON chunk metadata then a WAV blob per translated segment, keyed by the same `session_id` and `chunk_id` for highlighting.

## Notes
- Glossary terms live in `backend/app/glossary/do_not_translate.tsv` and are passed to both STT phrase hints and post-translation fixup.
- Segmentation uses punctuation plus silence to cut; adjust thresholds in `segmenter.py`.
- The old Daily.co bot and scripts have been removed. The previous Daily-based frontend remains in `client/` purely as a design reference; it is not wired to the new backend.
