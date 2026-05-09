"""
/transcribe — core STT endpoints.

POST /transcribe/file   — upload a WAV/MP3 file
POST /transcribe/raw    — send raw float32 audio bytes
GET  /transcribe/stream — SSE stream: starts recording, emits result when done
"""

from __future__ import annotations

import io
import logging
import struct
import threading

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.audio import AudioCapture
from backend.config import AppConfig, load_config
from backend.history import HistoryStore
from backend.output import TextOutput
from backend.postprocess import PostProcessor
from backend.stt.base import STTResult, TranscribeBackend, get_backend

logger = logging.getLogger("carefulwhisper.routers.transcribe")
router = APIRouter()

# Lazy singletons — initialized on first request
_cfg: AppConfig | None = None
_backend: TranscribeBackend | None = None
_capture: AudioCapture | None = None
_output: TextOutput | None = None
_pp = None
_history = None
_recording_lock = threading.Lock()
_recording_active = False


def _init():
    global _cfg, _backend, _capture, _output, _pp, _history
    if _cfg is None:
        _cfg = load_config()
        _backend = get_backend(_cfg.stt.backend)
        _backend.load(_cfg.stt.model, _cfg.stt.device, _cfg.stt.compute_type)
        _capture = AudioCapture(_cfg.audio)
        _output = TextOutput(_cfg.output)
        _pp = PostProcessor(_cfg.postprocess)
        _history = HistoryStore()


class TranscribeResponse(BaseModel):
    text: str
    language: str
    duration_s: float
    backend: str
    history_id: int | None = None


def _process_audio(audio: np.ndarray) -> TranscribeResponse:
    _init()
    assert _cfg is not None
    assert _backend is not None

    result: STTResult = _backend.transcribe(
        audio, _cfg.audio.sample_rate, _cfg.stt.language
    )  # type: ignore[union-attr]
    text = _pp.process(result.text)  # type: ignore[union-attr]

    hid = None
    if _cfg.history_enabled:  # type: ignore[union-attr]
        hid = _history.add(text, result.language, result.backend, result.duration_s)  # type: ignore[union-attr]

    return TranscribeResponse(
        text=text,
        language=result.language,
        duration_s=result.duration_s,
        backend=result.backend,
        history_id=hid,
    )


def start_recording_session() -> bool:
    """Start recording if not already active.

    Returns True if a new recording was started, False if already recording.
    """
    global _recording_active

    with _recording_lock:
        _init()
        if _recording_active:
            return False
        _capture.start()  # type: ignore[union-attr]
        _recording_active = True
        return True


def stop_recording_session(paste: bool = True) -> TranscribeResponse | None:
    """Stop active recording and run transcription pipeline.

    Returns None if recording is not currently active.
    """
    global _recording_active

    with _recording_lock:
        _init()
        if not _recording_active:
            return None

        audio = _capture.stop()  # type: ignore[union-attr]
        _recording_active = False
        resp = _process_audio(audio)
        if paste:
            _output.paste(resp.text)  # type: ignore[union-attr]
        return resp


@router.post("/file", response_model=TranscribeResponse)
async def transcribe_file(file: UploadFile = File(...)) -> TranscribeResponse:
    """Accept a WAV/MP3 upload and return transcription."""
    _init()
    try:
        import soundfile as sf  # type: ignore[import]

        data = await file.read()
        audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
        if sr != _cfg.audio.sample_rate:  # type: ignore[union-attr]
            import resampy  # type: ignore[import]

            audio = resampy.resample(audio, sr, _cfg.audio.sample_rate)  # type: ignore[union-attr]
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not decode audio: {exc}"
        ) from exc

    return _process_audio(audio)


@router.post("/raw", response_model=TranscribeResponse)
async def transcribe_raw(payload: dict) -> TranscribeResponse:
    """Accept raw float32 samples as a list (JSON) and return transcription."""
    samples = payload.get("samples", [])
    audio = np.array(samples, dtype=np.float32)
    return _process_audio(audio)


@router.post("/start")
async def recording_start() -> dict:
    """Tell the capture object to start recording."""
    started = start_recording_session()
    return {"status": "recording" if started else "already_recording"}


@router.post("/stop", response_model=TranscribeResponse)
async def recording_stop(paste: bool = True) -> TranscribeResponse:
    """Stop recording, transcribe, and optionally paste at cursor."""
    resp = stop_recording_session(paste=paste)
    if resp is None:
        raise HTTPException(status_code=409, detail="Not currently recording")
    return resp
