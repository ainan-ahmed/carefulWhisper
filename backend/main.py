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

import os
from pathlib import Path

def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key or not value or key in os.environ:
                continue
            os.environ[key] = value
    except Exception:
        logger.debug("Failed to load .env file", exc_info=True)

# Load env variables at module load time so it works under direct uvicorn and CLI runs
_load_env_file(Path.cwd() / ".env")


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
    import threading
    parser = argparse.ArgumentParser(description="carefulWhisper backend")
    parser.add_argument("--port", type=int, default=7331)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    def run_fastapi():
        # Running with reload=True in a background thread causes signals to crash Python
        uvicorn.run(
            "backend.main:app",
            host=args.host,
            port=args.port,
            reload=False,
            log_level="info",
        )

    # Start FastAPI in background
    t_api = threading.Thread(target=run_fastapi, daemon=True)
    t_api.start()

    # Start System Tray in MAIN thread (blocking)
    os.environ["PYSTRAY_BACKEND"] = "appindicator"
    try:
        from backend.tray import run_tray
        run_tray()
    except Exception as e:
        logger.error(f"Failed to start System Tray: {e}")
        # fallback
        import time
        while True:
            time.sleep(1)

if __name__ == "__main__":
    start()
