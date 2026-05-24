"""
Config loader — reads ~/.config/carefulwhisper/config.toml
Falls back to sane defaults if the file doesn't exist.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "carefulwhisper" / "config.toml"
DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.toml"


@dataclass
class STTConfig:
    backend: str = "faster_whisper"  # faster_whisper | parakeet | openai
    model: str = "base.en"  # Whisper model size
    language: str = "en"  # ISO 639-1 or "auto"
    device: str = "auto"  # cpu | cuda | auto
    compute_type: str = "int8"  # int8 | float16 | float32
    openai_api_key: str = ""
    fallback_to_cloud: bool = False


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    blocksize: int = 1024
    vad_enabled: bool = True
    vad_threshold: float = 0.5  # 0.0–1.0 silero sensitivity
    vad_min_silence_ms: int = 500  # ms of silence before stopping


@dataclass
class HotkeyConfig:
    combo: str = "<ctrl>+<alt>+space"  # pynput format
    mode: str = "hold"  # hold | toggle | always_on


@dataclass
class OutputConfig:
    method: str = "auto"  # auto | xdotool | ydotool | clipboard
    paste_delay_ms: int = 50
    add_trailing_space: bool = True


@dataclass
class PostProcessConfig:
    fix_punctuation: bool = True
    capitalize_sentences: bool = True
    custom_vocab: list[str] = field(default_factory=list)
    substitutions: dict[str, str] = field(default_factory=dict)
    remove_fillers: bool = False
    filler_words: list[str] = field(
        default_factory=lambda: [
            "um",
            "uh",
            "er",
            "ah",
            "hmm",
            "mm",
            "mhm",
            "uhh",
            "umm",
        ]
    )
    format_numbers: bool = False
    fix_unicode: bool = False
    handle_self_corrections: bool = False


@dataclass
class ProfileConfig:
    name: str = "default"
    stt: STTConfig = field(default_factory=STTConfig)
    postprocess: PostProcessConfig = field(default_factory=PostProcessConfig)


@dataclass
class LLMConfig:
    enabled: bool = False
    model: str = "gpt-4o-mini"
    system_prompt: str = (
        "You are a text-cleanup assistant. Return only the corrected text. "
        "Preserve meaning, tone, and language. Light paragraph formatting is fine, "
        "but do not add headings, lists, or explanations."
    )
    prompt: str = "Correct the grammar and punctuation of this text: {text}"
    trigger_phrase: str = "and fix this"
    auto_on_length_enabled: bool = False
    auto_on_length_threshold: int = 200


@dataclass
class AppConfig:
    stt: STTConfig = field(default_factory=STTConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    postprocess: PostProcessConfig = field(default_factory=PostProcessConfig)
    profiles: dict[str, ProfileConfig] = field(default_factory=dict)
    active_profile: str = "default"
    history_enabled: bool = True
    llm: LLMConfig = field(default_factory=LLMConfig)


def _merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base (base is mutated)."""
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    raw: dict = {}

    if path.exists():
        with open(path, "rb") as f:
            raw = tomllib.load(f)

    stt_raw = raw.get("stt", {})
    audio_raw = raw.get("audio", {})
    hotkey_raw = raw.get("hotkey", {})
    output_raw = raw.get("output", {})
    pp_raw = raw.get("postprocess", {})
    llm_raw = raw.get("llm", {})

    return AppConfig(
        stt=STTConfig(**{k: v for k, v in stt_raw.items() if hasattr(STTConfig, k)}),
        audio=AudioConfig(
            **{k: v for k, v in audio_raw.items() if hasattr(AudioConfig, k)}
        ),
        hotkey=HotkeyConfig(
            **{k: v for k, v in hotkey_raw.items() if hasattr(HotkeyConfig, k)}
        ),
        output=OutputConfig(
            **{k: v for k, v in output_raw.items() if hasattr(OutputConfig, k)}
        ),
        postprocess=PostProcessConfig(
            **{k: v for k, v in pp_raw.items() if hasattr(PostProcessConfig, k)}
        ),
        llm=LLMConfig(**{k: v for k, v in llm_raw.items() if hasattr(LLMConfig, k)}),
        active_profile=raw.get("active_profile", "default"),
        history_enabled=raw.get("history_enabled", True),
    )


def write_config(section: str, data: dict, path: Path = CONFIG_PATH) -> dict:
    """Update a single config section, merge into existing file, and return updated values."""
    import tomli_w

    # Read existing config
    raw: dict = {}
    if path.exists():
        with open(path, "rb") as f:
            raw = tomllib.load(f)

    if section == "general":
        # Top-level keys
        for k, v in data.items():
            raw[k] = v
    else:
        current = raw.get(section, {})
        current.update(data)
        raw[section] = current

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(raw, f)

    return raw.get(section, data) if section != "general" else {
        k: raw.get(k) for k in data
    }


def write_default_config(path: Path = CONFIG_PATH) -> None:
    """Write a starter config file if none exists."""
    import tomli_w

    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = AppConfig()
    data = {
        "active_profile": cfg.active_profile,
        "history_enabled": cfg.history_enabled,
        "stt": {
            "backend": cfg.stt.backend,
            "model": cfg.stt.model,
            "language": cfg.stt.language,
            "device": cfg.stt.device,
            "compute_type": cfg.stt.compute_type,
            "fallback_to_cloud": cfg.stt.fallback_to_cloud,
        },
        "audio": {
            "sample_rate": cfg.audio.sample_rate,
            "vad_enabled": cfg.audio.vad_enabled,
            "vad_threshold": cfg.audio.vad_threshold,
            "vad_min_silence_ms": cfg.audio.vad_min_silence_ms,
        },
        "hotkey": {
            "combo": cfg.hotkey.combo,
            "mode": cfg.hotkey.mode,
        },
        "output": {
            "method": cfg.output.method,
            "paste_delay_ms": cfg.output.paste_delay_ms,
            "add_trailing_space": cfg.output.add_trailing_space,
        },
        "postprocess": {
            "fix_punctuation": cfg.postprocess.fix_punctuation,
            "capitalize_sentences": cfg.postprocess.capitalize_sentences,
            "custom_vocab": cfg.postprocess.custom_vocab,
            "substitutions": cfg.postprocess.substitutions,
            "remove_fillers": cfg.postprocess.remove_fillers,
            "filler_words": cfg.postprocess.filler_words,
            "format_numbers": cfg.postprocess.format_numbers,
            "fix_unicode": cfg.postprocess.fix_unicode,
            "handle_self_corrections": cfg.postprocess.handle_self_corrections,
        },
        "llm": {
            "enabled": cfg.llm.enabled,
            "model": cfg.llm.model,
            "system_prompt": cfg.llm.system_prompt,
            "prompt": cfg.llm.prompt,
            "trigger_phrase": cfg.llm.trigger_phrase,
            "auto_on_length_enabled": cfg.llm.auto_on_length_enabled,
            "auto_on_length_threshold": cfg.llm.auto_on_length_threshold,
        },
    }
    with open(path, "wb") as f:
        tomli_w.dump(data, f)
