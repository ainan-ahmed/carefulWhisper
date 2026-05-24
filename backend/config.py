"""
Config loader — reads ~/.config/carefulwhisper/config.toml
Falls back to sane defaults if the file doesn't exist.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from pydantic import BaseModel, Field

CONFIG_PATH = Path.home() / ".config" / "carefulwhisper" / "config.toml"
DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.toml"


class STTConfig(BaseModel):
    backend: str = "faster_whisper"  # faster_whisper | parakeet | openai
    model: str = "base.en"  # Whisper model size
    language: str = "en"  # ISO 639-1 or "auto"
    device: str = "auto"  # cpu | cuda | auto
    compute_type: str = "int8"  # int8 | float16 | float32
    openai_api_key: str = ""
    fallback_to_cloud: bool = False


class AudioConfig(BaseModel):
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    channels: int = Field(default=1, ge=1, le=2)
    blocksize: int = Field(default=1024, ge=128, le=8192)
    vad_enabled: bool = True
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)  # 0.0–1.0 silero sensitivity
    vad_min_silence_ms: int = Field(default=500, ge=50, le=5000)  # ms of silence before stopping


class HotkeyConfig(BaseModel):
    combo: str = "<ctrl>+<alt>+space"  # pynput format
    mode: str = "hold"  # hold | toggle | always_on


class OutputConfig(BaseModel):
    method: str = "auto"  # auto | xdotool | ydotool | clipboard
    paste_delay_ms: int = Field(default=50, ge=0, le=5000)
    add_trailing_space: bool = True


class PostProcessConfig(BaseModel):
    fix_punctuation: bool = True
    capitalize_sentences: bool = True
    custom_vocab: list[str] = Field(default_factory=list)
    substitutions: dict[str, str] = Field(default_factory=dict)
    remove_fillers: bool = False
    filler_words: list[str] = Field(
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


class ProfileConfig(BaseModel):
    name: str = "default"
    stt: STTConfig = Field(default_factory=STTConfig)
    postprocess: PostProcessConfig = Field(default_factory=PostProcessConfig)


class LLMConfig(BaseModel):
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
    auto_on_length_threshold: int = Field(default=200, ge=0, le=100000)


class AppConfig(BaseModel):
    stt: STTConfig = Field(default_factory=STTConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    postprocess: PostProcessConfig = Field(default_factory=PostProcessConfig)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)
    active_profile: str = "default"
    history_enabled: bool = True
    llm: LLMConfig = Field(default_factory=LLMConfig)


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
        try:
            with open(path, "rb") as f:
                raw = tomllib.load(f)
        except Exception as e:
            import logging
            logging.getLogger("carefulwhisper.config").error(
                "Failed to parse config TOML file: %s. Reverting to defaults.", e
            )
            return AppConfig()

    try:
        return AppConfig.model_validate(raw)
    except Exception as e:
        import logging
        logging.getLogger("carefulwhisper.config").warning(
            "Config validation failed: %s. Using default fallback configuration.", e
        )
        return AppConfig()


_SECTION_MODELS = {
    "stt": STTConfig,
    "audio": AudioConfig,
    "hotkey": HotkeyConfig,
    "output": OutputConfig,
    "postprocess": PostProcessConfig,
    "llm": LLMConfig,
}


def write_config(section: str, data: dict, path: Path = CONFIG_PATH) -> dict:
    """Update a single config section, merge into existing file, and return updated values."""
    import tomli_w

    # Read existing config
    raw: dict = {}
    if path.exists():
        try:
            with open(path, "rb") as f:
                raw = tomllib.load(f)
        except Exception:
            pass

    if section == "general":
        temp_raw = dict(raw)
        for k, v in data.items():
            temp_raw[k] = v
        # Validate AppConfig to ensure general keys are safe
        validated_app = AppConfig.model_validate(temp_raw)
        
        # Save back the keys
        for k in data:
            raw[k] = getattr(validated_app, k)
            
        ret_val = {k: raw.get(k) for k in data}
    else:
        model_cls = _SECTION_MODELS.get(section)
        if not model_cls:
            raise ValueError(f"Unknown config section: {section}")
            
        current = raw.get(section, {})
        # Merge updates
        merged = {**current, **data}
        # Validate through Pydantic
        validated_section = model_cls.model_validate(merged)
        # Dump back to dictionary
        dumped = validated_section.model_dump()
        raw[section] = dumped
        ret_val = dumped

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(raw, f)

    return ret_val


def write_default_config(path: Path = CONFIG_PATH) -> None:
    """Write a starter config file if none exists."""
    import tomli_w

    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = AppConfig()
    data = cfg.model_dump()
    with open(path, "wb") as f:
        tomli_w.dump(data, f)
