"""
carefulWhisper backend — FastAPI app + sidecar entrypoint.
Run directly:  uv run uvicorn backend.main:app --port 7331 --reload
Or via CLI:    uv run carefulwhisper
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import load_config
from backend.hotkey import HotkeyManager
from backend.routers import audio, history, settings, transcribe

logger = logging.getLogger("carefulwhisper")


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app

    cfg = load_config()
    hotkey = HotkeyManager(cfg.hotkey)

    def _on_hotkey_start() -> None:
        try:
            started = transcribe.start_recording_session()
            if started:
                logger.debug("Hotkey start: recording started")
        except Exception:
            logger.exception("Hotkey start callback failed")

    def _on_hotkey_stop() -> None:
        try:
            resp = transcribe.stop_recording_session(paste=True)
            if resp is None:
                logger.debug("Hotkey stop ignored: no active recording")
            else:
                logger.debug("Hotkey stop: transcribed via %s", resp.backend)
        except Exception:
            logger.exception("Hotkey stop callback failed")

    hotkey.register(_on_hotkey_start, _on_hotkey_stop)

    logger.info(
        "carefulWhisper starting — backend: %s, model: %s",
        cfg.stt.backend,
        cfg.stt.model,
    )
    try:
        hotkey.start()
    except Exception:
        logger.exception("Failed to start global hotkey listener")

    yield

    try:
        hotkey.stop()
    except Exception:
        logger.exception("Failed to stop global hotkey listener cleanly")


app = FastAPI(
    title="carefulWhisper",
    version="0.1.0",
    description="Local-first STT daemon with cloud fallback",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["tauri://localhost", "http://localhost:*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(transcribe.router, prefix="/transcribe", tags=["transcribe"])
app.include_router(audio.router, prefix="/audio", tags=["audio"])
app.include_router(history.router, prefix="/history", tags=["history"])
app.include_router(settings.router, prefix="/settings", tags=["settings"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ── CLI entrypoint (uv run carefulwhisper) ────────────────────────────────────
def start() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="carefulWhisper backend")
    parser.add_argument("--port", type=int, default=7331)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    start()
