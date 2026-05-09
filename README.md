# carefulWhisper 🎙️

**carefulWhisper** is a local-first dictation backend for fast speech-to-text and paste-to-cursor workflows.
It is built with **FastAPI** + **faster-whisper**, with global hotkey and text output integration.

✨ **Desktop integration friendly, API-first backend** ✨

[![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Whisper](https://img.shields.io/badge/STT-faster--whisper-1f2937)](https://github.com/SYSTRAN/faster-whisper)
[![Platform](https://img.shields.io/badge/Platform-Desktop-blue)](#)

---

## 🚀 Quick Start

### Option A: Script Entrypoint (Recommended)

```bash
uv sync
uv run carefulwhisper
```

With custom options:

```bash
uv run carefulwhisper --host 127.0.0.1 --port 7331 --reload
```

### Option B: Uvicorn directly

```bash
uv sync
uv run uvicorn backend.main:app --port 7331 --reload
```

### Option C: Module Entrypoint

```bash
uv sync
uv run python -m backend.main --port 7331 --reload
```

> **Wayland users**: `ydotool` requires its daemon to be running before starting the app.
> ```bash
> systemctl --user enable --now ydotool  # permanent
> # or: ydotoold &                        # current session only
> ```

### Health Check

```bash
curl http://127.0.0.1:7331/health
```

---

## ✨ Current Capabilities

- Global hotkey dictation flow (`/transcribe/start` + `/transcribe/stop`)
- File and raw transcription endpoints (`/transcribe/file`, `/transcribe/raw`)
- Output auto-selection (`ydotool`/`xdotool`/clipboard fallback)
- History, audio device listing, and settings endpoints

---

## 🧭 Runtime Notes

- STT model is loaded once per process (lazy singleton) and reused.
- Wayland on Linux prefers `evdev` for hotkeys; other sessions use `pynput`.
- Config path: `~/.config/carefulwhisper/config.toml`

---

## 📚 Project Docs

- `AGENTS.md` — high-signal repo instructions for coding agents
- `WORKFLOW.md` — backend execution flow and request lifecycle
