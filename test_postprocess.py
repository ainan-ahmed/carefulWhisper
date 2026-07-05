#!/usr/bin/env python3
"""Test postprocessing features with real audio samples.

Usage:
    uv run python test_postprocess.py [wav_file ...]

If no files are given, tests all WAV files in test_samples/.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from backend.config import AppConfig, PostProcessConfig
from backend.postprocess import PostProcessor
from backend.stt.base import get_backend

SAMPLES_DIR = Path(__file__).parent / "test_samples"


def transcribe_file(wav_path: Path) -> tuple[str, float]:
    """Transcribe a WAV file and return (raw_text, duration_s)."""
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)

    cfg = AppConfig()
    backend = get_backend(cfg.stt.backend)
    print(f"  Loading model {cfg.stt.model!r} on {cfg.stt.device}...")
    t0 = time.time()
    backend.load(cfg.stt.model, cfg.stt.device, cfg.stt.compute_type)
    load_time = time.time() - t0
    print(f"  Model loaded in {load_time:.1f}s")

    if sr != cfg.audio.sample_rate:
        import resampy

        audio = resampy.resample(audio, sr, cfg.audio.sample_rate)

    print(f"  Transcribing {wav_path.name} ({len(audio)/cfg.audio.sample_rate:.1f}s audio)...")
    t0 = time.time()
    result = backend.transcribe(audio, cfg.audio.sample_rate, cfg.stt.language)
    transcribe_time = time.time() - t0
    print(f"  Transcription took {transcribe_time:.1f}s")

    return result.text, result.duration_s


def test_postprocessing(raw_text: str) -> None:
    """Run raw text through various postprocessing configs and compare."""
    configs: list[tuple[str, PostProcessConfig]] = [
        ("Raw (no postprocessing)", PostProcessConfig(
            fix_punctuation=False, capitalize_sentences=False,
        )),
        ("Default (punct + caps)", PostProcessConfig()),
        ("+ Filler removal", PostProcessConfig(remove_fillers=True)),
        ("+ Number formatting", PostProcessConfig(format_numbers=True)),
        ("+ Unicode fix", PostProcessConfig(fix_unicode=True)),
        ("+ Self-correction", PostProcessConfig(handle_self_corrections=True)),
        ("All features enabled", PostProcessConfig(
            remove_fillers=True, format_numbers=True,
            fix_unicode=True, handle_self_corrections=True,
        )),
    ]

    print()
    print("  " + "=" * 70)
    for label, cfg in configs:
        pp = PostProcessor(cfg, LLMConfig(enabled=False))
        mode, processed = pp.process(raw_text)
        print(f"  {label}:")
        print(f"    [{mode.upper()}] {processed}")
        print()


def main() -> None:
    wav_files: list[Path] = []
    if len(sys.argv) > 1:
        wav_files = [Path(a) for a in sys.argv[1:]]
    else:
        wav_files = sorted(SAMPLES_DIR.glob("*.wav"))

    if not wav_files:
        print(f"No WAV files found in {SAMPLES_DIR}")
        sys.exit(1)

    for wav_path in wav_files:
        if not wav_path.exists():
            print(f"SKIP: {wav_path} not found")
            continue

        print(f"\n{'=' * 70}")
        print(f"Testing: {wav_path.name} ({wav_path.stat().st_size / 1024:.0f} KB)")
        print("=" * 70)

        raw_text, duration = transcribe_file(wav_path)
        print(f"\n  Raw STT output:")
        print(f"    {raw_text!r}")
        print(f"  Duration: {duration:.1f}s")

        test_postprocessing(raw_text)

    print("Done.")


if __name__ == "__main__":
    main()
