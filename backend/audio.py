"""
Audio capture.
Uses sounddevice for cross-platform mic input.
VAD (silence trimming) is delegated to faster-whisper's built-in vad_filter.
"""

from __future__ import annotations

import logging
import queue

import numpy as np
import sounddevice as sd

from backend.config import AudioConfig

logger = logging.getLogger("carefulwhisper.audio")


class AudioCapture:
    """
    Blocking microphone recorder.
    Call start() → stop() to get a float32 numpy array.
    """

    def __init__(self, cfg: AudioConfig) -> None:
        self.cfg = cfg
        self._q: queue.Queue[np.ndarray] = queue.Queue()
        self._recording = False
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time: object,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.warning("Audio status: %s", status)
        if self._recording:
            self._q.put(indata.copy().flatten())

    def start(self) -> None:
        self._frames.clear()
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.cfg.sample_rate,
            channels=self.cfg.channels,
            blocksize=self.cfg.blocksize,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        logger.debug("Recording started")

    def stop(self) -> np.ndarray:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._recording = False

        # drain queue
        while True:
            try:
                self._frames.append(self._q.get_nowait())
            except queue.Empty:
                break

        audio = (
            np.concatenate(self._frames)
            if self._frames
            else np.zeros(1, dtype="float32")
        )
        logger.debug(
            "Recording stopped — %.2fs captured", len(audio) / self.cfg.sample_rate
        )
        return audio

    def list_devices(self) -> list[dict]:
        devices = sd.query_devices()
        return [
            {"index": i, "name": d["name"], "channels": d["max_input_channels"]}
            for i, d in enumerate(devices)  # type: ignore[arg-type]
            if d["max_input_channels"] > 0
        ]
