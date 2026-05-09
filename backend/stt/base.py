"""Abstract base class and backend factory for all STT backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class STTResult:
    text: str
    language: str
    duration_s: float
    backend: str
    confidence: float | None = None  # 0.0–1.0 if backend supports it


class TranscribeBackend(ABC):
    @abstractmethod
    def load(
        self, model: str, device: str = "auto", compute_type: str = "int8"
    ) -> None:
        """Load / warm up the model."""
        ...

    @abstractmethod
    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: str = "en",
    ) -> STTResult:
        """Transcribe a float32 mono audio array."""
        ...

    @property
    @abstractmethod
    def name(self) -> str: ...


def get_backend(name: str) -> TranscribeBackend:
    """Return an instance of the requested STT backend.

    Supported values for *name* (matches STTConfig.backend):
      - "faster_whisper"  — local CTranslate2-based Whisper (default)

    Raises ValueError for unknown names so misconfiguration is caught early.
    """
    if name == "faster_whisper":
        from backend.stt.faster_whisper import FasterWhisperBackend  # noqa: PLC0415

        return FasterWhisperBackend()

    # Future backends:
    # if name == "openai":
    #     from backend.stt.openai import OpenAIBackend
    #     return OpenAIBackend()

    raise ValueError(f"Unknown STT backend: {name!r}. Valid options: 'faster_whisper'")
