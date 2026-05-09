# carefulWhisper Workflow

This file describes the current backend execution flow and where each component fits.

## 1) Process startup

1. Start server (`uv run uvicorn backend.main:app --port 7331 --reload`) or CLI (`uv run carefulwhisper`).
2. `backend/main.py` creates the FastAPI app and mounts routers:
   - `/transcribe`
   - `/audio`
   - `/history`
   - `/settings`
3. `lifespan()` loads config, registers `HotkeyManager` callbacks, and starts global hotkey listening.

## 2) Lazy runtime initialization

`backend/routers/transcribe.py` uses lazy singletons in `_init()`:

- `load_config()`
- `get_backend(...)`
- `_backend.load(model, device, compute_type)`
- `AudioCapture`
- `TextOutput`
- `PostProcessor`
- `HistoryStore`

Important: the STT model is loaded once per process (on first request), then reused.

## 3) Live dictation flow (`/transcribe/start` -> `/transcribe/stop`)

1. `/transcribe/start`
   - Calls `start_recording_session()`.
   - Internally uses a lock and only starts once while active.
2. `/transcribe/stop`
   - Calls `stop_recording_session(paste=...)`.
   - Returns 409 if recording was not active.
3. `_process_audio(...)`
   - `_backend.transcribe(audio, sample_rate, language)`
   - `PostProcessor.process(text)`
   - Optional history write via `HistoryStore.add(...)`
   - Returns `TranscribeResponse`
4. If `paste=true`, `TextOutput.paste(text)` sends text to active app.

## 4) File transcription flow (`/transcribe/file`)

1. Read upload bytes.
2. Decode with `soundfile`.
3. Resample with `resampy` if sample rate differs from config.
4. Reuse `_process_audio(...)` pipeline.

## 5) Raw transcription flow (`/transcribe/raw`)

1. JSON `samples` -> `numpy.float32` array.
2. Reuse `_process_audio(...)` pipeline.

## 6) Output method selection

`backend/output.py` auto-detects output strategy:

- Wayland: prefer `ydotool`, fallback to clipboard.
- Non-Wayland: prefer `xdotool`, fallback to clipboard.

## 7) Hotkey backend selection and trigger flow

`backend/hotkey.py` chooses input backend by environment:

- Linux + `XDG_SESSION_TYPE=wayland`: use `evdev`.
- Otherwise: use `pynput`.

Both `hold` and `toggle` modes are supported.

In `backend/main.py`, hotkey callbacks call:

- start callback -> `transcribe.start_recording_session()`
- stop callback -> `transcribe.stop_recording_session(paste=True)`
