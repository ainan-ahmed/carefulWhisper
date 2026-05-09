# carefulWhisper Agent Notes

## Reality checks first

- No CI, pre-commit, lint, mypy, or pytest config is present; do targeted runtime/syntax checks.
- `README.md` is now accurate; trust code in `backend/` and `pyproject.toml` for implementation details.

## Commands that actually work

- Sync dependencies: `uv sync`
- Run dev server: `uv run uvicorn backend.main:app --port 7331 --reload`
- CLI entrypoint: `uv run carefulwhisper` (wired to `backend.main:start`)
- Fast sanity check: `uv run python -m py_compile backend/main.py backend/routers/transcribe.py backend/hotkey.py`
- Health check: `curl http://127.0.0.1:7331/health`

## Core execution flow

- App startup (`backend/main.py`) loads config and starts `HotkeyManager` in FastAPI lifespan.
- Hotkey callbacks call `transcribe.start_recording_session()` / `transcribe.stop_recording_session(paste=True)`.
- STT model load is lazy-singleton in `backend/routers/transcribe.py::_init()` (loaded once per process, then reused).
- Recording state is lock-protected; `/transcribe/stop` returns HTTP 409 when no active recording.
- `backend/routers/transcribe.py` docstring mentions `/transcribe/stream`, but no stream endpoint is currently implemented.

## Wayland/Linux gotchas

- Hotkey backend selection: Linux + `XDG_SESSION_TYPE=wayland` -> `evdev`; otherwise `pynput`.
- `evdev` hotkeys require read access to `/dev/input/event*`; permission failures fall back to `pynput`.
- Output auto mode: Wayland prefers `ydotool`; non-Wayland prefers `xdotool`; both can fall back to clipboard.
- Clipboard fallback (`backend/output.py`) uses `pyperclip` **and** `xdotool key ctrl+v`; missing `xdotool` breaks paste.
- External binaries (`ydotool` / `xdotool`) are runtime requirements, not Python dependencies.

## Paths and naming mismatches

- Config path: `~/.config/carefulwhisper/config.toml`.
- History DB path: `~/.local/share/carefulwhisper/history.db`.
- Logger namespace is unified: `carefulwhisper.*`.

## Dependency notes (currently used by runtime code)

- Audio/file/transcribe/output/hotkey paths rely on: `soundfile`, `resampy`, `pyperclip`, `pynput`, `evdev`.

## Keep docs aligned

- `WORKFLOW.md` is currently code-aligned; update it whenever touching startup lifecycle, hotkey wiring, or transcribe flow.
