"""Settings read/write endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from backend.config import load_config, write_config, write_default_config

router = APIRouter()

_VALID_SECTIONS = {"stt", "audio", "hotkey", "output", "postprocess", "llm", "general"}


@router.get("/")
def get_settings() -> dict:
    cfg = load_config()
    return {
        "stt": cfg.stt.model_dump(),
        "audio": cfg.audio.model_dump(),
        "hotkey": cfg.hotkey.model_dump(),
        "output": cfg.output.model_dump(),
        "postprocess": cfg.postprocess.model_dump(),
        "llm": cfg.llm.model_dump(),
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

    try:
        updated = write_config(section, body)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"message": "Validation failed", "errors": e.errors(include_url=False)},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "saved", "section": section, "values": updated}


@router.post("/reset")
def reset_settings() -> dict:
    write_default_config()
    return {"status": "reset"}

