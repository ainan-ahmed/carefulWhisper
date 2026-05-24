"""Settings read/write endpoints."""

from fastapi import APIRouter, HTTPException, Request

from backend.config import AppConfig, load_config, write_config, write_default_config

router = APIRouter()

_VALID_SECTIONS = {"stt", "audio", "hotkey", "output", "postprocess", "llm", "general"}


@router.get("/")
def get_settings() -> dict:
    cfg = load_config()
    return {
        "stt": vars(cfg.stt),
        "audio": vars(cfg.audio),
        "hotkey": vars(cfg.hotkey),
        "output": vars(cfg.output),
        "postprocess": vars(cfg.postprocess),
        "llm": vars(cfg.llm),
        "active_profile": cfg.active_profile,
        "history_enabled": cfg.history_enabled,
    }


@router.patch("/{section}")
async def patch_settings(section: str, request: Request) -> dict:
    """Update a single config section with the provided key-value pairs."""
    if section not in _VALID_SECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown section '{section}'. Valid: {sorted(_VALID_SECTIONS)}",
        )
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    updated = write_config(section, body)
    return {"status": "saved", "section": section, "values": updated}


@router.post("/reset")
def reset_settings() -> dict:
    write_default_config()
    return {"status": "reset"}
