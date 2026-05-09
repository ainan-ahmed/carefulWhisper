"""Audio device listing endpoint."""

from fastapi import APIRouter

from backend.audio import AudioCapture
from backend.config import load_config

router = APIRouter()


@router.get("/devices")
def list_devices() -> list[dict]:
    cfg = load_config()
    cap = AudioCapture(cfg.audio)
    return cap.list_devices()
