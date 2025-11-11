# Daily Multi Translation – React Client

This Vite + React application provides a richer interface for the Daily multi-language
translation bot:

1. Paste a Daily room URL (produced by `server.py` when you hit `/`) and press **Join**.
2. Toggle which translated languages you want to follow (English is intentionally omitted).
3. Listen to each translated audio track independently.
4. Watch real-time transcript updates for every selected language.

## Getting Started

```bash
cd client
npm install          # install dependencies (requires network access)
npm run dev -- --host  # start Vite dev server on http://localhost:5173
```

When you are ready to produce a static build:

```bash
npm run build
```

The production-ready assets will be written to `client/dist/`, which you can serve from any
static host or wire into the FastAPI application if desired.
