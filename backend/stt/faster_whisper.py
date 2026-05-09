"""faster-whisper local STT backend."""

from __future__ import annotations

import logging
import time

import numpy as np

from backend.stt.base import STTResult, TranscribeBackend

logger = logging.getLogger("carefulwhisper.stt.faster_whisper")


class FasterWhisperBackend(TranscribeBackend):
    def __init__(self) -> None:
        self._model: object = None

    @property
    def name(self) -> str:
        return "faster_whisper"

    def load(
        self, model: str = "base.en", device: str = "auto", compute_type: str = "int8"
    ) -> None:
        from faster_whisper import WhisperModel  # type: ignore[import]

        _device = device

        logger.info(
            "Loading faster-whisper model=%s device=%s compute=%s",
            model,
            _device,
            compute_type,
        )
        self._model = WhisperModel(model, device=_device, compute_type=compute_type)
        logger.info("faster-whisper ready")

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str = "en",
    ) -> STTResult:
        if self._model is None:
            raise RuntimeError("Model not loaded — call load() first")

        t0 = time.perf_counter()
        lang = None if language == "auto" else language

        segments, info = self._model.transcribe(  # type: ignore[attr-defined]
            audio,
            language=lang,
            beam_size=5,
            vad_filter=True,
        )

        text = " ".join(s.text.strip() for s in segments).strip()
        elapsed = time.perf_counter() - t0

        logger.debug("Transcribed in %.3fs: %r", elapsed, text[:80])

        return STTResult(
            text=text,
            language=info.language,
            duration_s=elapsed,
            backend=self.name,
        )
