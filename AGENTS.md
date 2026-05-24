# carefulWhisper Agent Notes

## Reality checks first

- No CI, pre-commit, lint, mypy, or pytest config is present; do targeted runtime/syntax checks.
- `README.md` is now accurate; trust code in `backend/` and `pyproject.toml` for implementation details.

## Commands that actually work

- Sync dependencies: `uv sync`
- Run dev server: `uv run uvicorn backend.main:app --port 7331 --reload`
- CLI entrypoint: `uv run carefulwhisper` (wired to `backend.main:start`)
- Run Slint UI standalone: `uv run python -m ui`
- Fast sanity check: `uv run python -m py_compile backend/main.py backend/routers/transcribe.py backend/hotkey.py ui/main.py`
- Health check: `curl http://127.0.0.1:7331/health`
- Test postprocessing features: `uv run python test_postprocess.py [wav_file_path]`

## Core execution flow

- App startup (`backend/main.py`) loads config and starts `HotkeyManager` in FastAPI lifespan.
- Hotkey callbacks call `transcribe.start_recording_session()` / `transcribe.stop_recording_session(paste=True)`.
- STT model load is lazy-singleton in `backend/routers/transcribe.py::_init()` (loaded once per process, then reused).
- Recording state is lock-protected; `/transcribe/stop` returns HTTP 409 when no active recording.
- Backend STT endpoints `/transcribe/start` and `/transcribe/stop` MUST be synchronous `def` endpoints (not `async def`) so they execute in an external thread pool and do not block the main FastAPI ASGI event loop during heavy CPU-bound transcription.
- A thread-safe global `_auto_stop_timer` daemon `threading.Timer` automatically triggers `stop_recording_session(paste=True)` after **180 seconds** (3 minutes) of recording as a failsafe duration guard.
- Standalone Slint UI (`ui/`) uses an asynchronous event loop via `slint.run_event_loop()` to keep standard `asyncio` active.
- The UI polls `/transcribe/status` in a background daemon thread and dispatches updates thread-safely via the loop's `loop.call_soon_threadsafe(update_ui)` method.
- The UI's Home page microphone circle badge is clickable, executing non-blocking POST requests asynchronously inside `asyncio.to_thread`.
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
- Postprocessing relies on: `text2num` (number formatting) and `ftfy` (unicode fixes).
- Slint Desktop UI package relies on: `slint`.

## Keep docs aligned

- `WORKFLOW.md` is currently code-aligned; update it whenever touching startup lifecycle, hotkey wiring, or transcribe flow.
