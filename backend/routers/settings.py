"""Settings read/write endpoints."""

from fastapi import APIRouter

from backend.config import AppConfig, load_config, write_default_config

router = APIRouter()


@router.get("/")
def get_settings() -> dict:
    cfg = load_config()
    return {
        "stt": vars(cfg.stt),
        "audio": vars(cfg.audio),
        "hotkey": vars(cfg.hotkey),
        "output": vars(cfg.output),
        "postprocess": vars(cfg.postprocess),
        "active_profile": cfg.active_profile,
        "history_enabled": cfg.history_enabled,
    }


@router.post("/reset")
def reset_settings() -> dict:
    write_default_config()
    return {"status": "reset"}
