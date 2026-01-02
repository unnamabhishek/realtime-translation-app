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

## OBS streaming (macOS)
Use OBS as the encoder and push to Twitch. Route TTS audio to a virtual device and use a browser source for captions.
1) Start the backend + web app as above.
2) Run the audio bridge to play TTS locally: `cd backend/device && python obs_audio_bridge.py` (set `SESSION_ID`, `TARGET`, `BACKEND_URL` in the script).
3) In macOS, route system output to a virtual device (BlackHole/Loopback). In OBS, add an Audio Input Capture for that device.
4) In OBS, add a Browser Source pointing to `http://localhost:3000/overlay?session=<id>&target=hi-IN&backend=http://localhost:8080`.

## Protocols
- Ingest WS: first message JSON `{"session_id":"<uuid>","lang_src":"en-US","targets":["hi-IN"]}`, subsequent frames raw PCM16 mono 16k.
- Out WS: server sends JSON chunk metadata then a WAV blob per translated segment, keyed by the same `session_id` and `chunk_id` for highlighting.

## Notes
- Glossary terms live in `backend/app/glossary/do_not_translate.tsv` and are passed to STT phrase hints and translation protection.
- Segmentation uses punctuation plus silence to cut; adjust thresholds in `segmenter.py`.
- The old Daily.co bot and scripts have been removed. The previous Daily-based frontend remains in `client/` purely as a design reference; it is not wired to the new backend.
