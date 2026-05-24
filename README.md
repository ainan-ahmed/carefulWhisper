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

### Option D: Slint Desktop UI (Standalone)

```bash
uv sync
uv run python -m ui
```

> **System Tray Launch**: Once the backend is running, you can also launch the Slint UI directly by clicking **"Open Slint UI"** from the system tray context menu.

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

- Native desktop **Slint GUI** (tabbed interface featuring a dynamic Home state, interactive click-to-toggle dictation, real-time transcription loading indicator, and a complete History search dashboard with text copying and delete confirmation)
- Global hotkey dictation flow (`/transcribe/start` + `/transcribe/stop`)
- Failsafe recording duration guard (automatically cuts off and transcribes after 180s of recording to protect hardware)
- File and raw transcription endpoints (`/transcribe/file`, `/transcribe/raw`, `GET /transcribe/status`)
- Output auto-selection (`ydotool`/`xdotool`/clipboard fallback)
- Robust text postprocessing (filler removal, number formatting via `text2num`, unicode fixing via `ftfy`, smart punctuation/capitalization that preserves domains)
- History (SQLite), audio device listing, and settings endpoints

---

## 🧭 Runtime Notes

- STT model is loaded once per process (lazy singleton) and reused.
- Wayland on Linux prefers `evdev` for hotkeys; other sessions use `pynput`.
- Config path: `~/.config/carefulwhisper/config.toml`

---

## 📚 Project Docs

- `AGENTS.md` — high-signal repo instructions for coding agents
- `WORKFLOW.md` — backend and frontend event loops, request lifecycles, and polling sync
- `ui/` — package directory containing Slint templates, types, and theme definitions
