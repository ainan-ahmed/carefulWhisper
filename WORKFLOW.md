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

## 3) Live dictation flow (`/transcribe/start` -> `/transcribe/stop` -> `/transcribe/status`)

1. `/transcribe/start`
   - Calls `start_recording_session()`.
   - Internally uses a lock and only starts once while active.
   - Sets global `_current_state = "recording"`.
   - Schedules a **180-second** background daemon `threading.Timer` as a failsafe guard to automatically stop recording if the user forgets.
2. `/transcribe/stop`
   - Calls `stop_recording_session(paste=...)`.
   - Returns 409 if recording was not active.
   - Sets global `_current_state = "transcribing"`.
   - Under the lock, cancels the active `_auto_stop_timer` failsafe.
   - Processes audio, runs transcription, and resets `_current_state = "idle"` inside a `finally` block.
3. `/transcribe/status`
   - Returns the current global state `{"status": _current_state}`.
4. `_process_audio(...)`
   - Temporarily transitions `_current_state` to `"transcribing"` if currently `"idle"` (for direct file/raw routes).
   - `_backend.transcribe(audio, sample_rate, language)`
   - `PostProcessor.process(text)`
   - Optional history write via `HistoryStore.add(...)`
   - Returns `TranscribeResponse`
5. If `paste=true`, `TextOutput.paste(text)` sends text to active app.

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

## 8) Slint UI status polling and state sync

1. Standalone UI launched via `backend/tray.py` or manually (`python -m ui`).
2. Starts a background thread in `ui/main.py` that polls the backend status endpoint (`GET /transcribe/status`) every 250ms.
3. Marshals state changes thread-safely to the Slint GUI thread via the `asyncio` event loop's `loop.call_soon_threadsafe()` method.
4. The Slint UI exposes `recording-status` to components:
   - `HomePage` displays high-fidelity responsive screens for `"idle"`, `"recording"` (pulsing badge, Listening... text, hotkey micro-hints), and `"transcribing"` (spinning indicator, converting voice to text hint).
   - The `HomePage` microphone badge is fully interactive. Clicking it when `"idle"` fires `toggle-recording` callback to send `POST /transcribe/start`. Clicking it when `"recording"` fires the callback to send `POST /transcribe/stop` (ignored when `"transcribing"`).
   - `HistoryPage` displays live statuses (`🔴 Recording...` or `⚙️ Transcribing...`) in the bottom status bar.
5. On `"transcribing" -> "idle"` transition, the UI automatically refreshes the transcript database list so new dictations appear instantly.

## 9) Settings Management and State Sync

1. **Initialization**: On Slint UI startup (`ui/main.py`), the app calls `_load_settings()` which fires an asynchronous HTTP `GET /settings/` request to the daemon. If the daemon is unreachable (e.g., in a standalone GUI run prior to backend start), it falls back to loading directly via `backend.config.load_config()`.
2. **UI Binding**: The settings dictionary is parsed and bound to 7 separate Slint property structs:
   - `settings_stt`: backend, model, language, device, compute_type, openai_api_key, fallback_to_cloud
   - `settings_audio`: sample_rate, channels, blocksize, vad_enabled, vad_threshold, vad_min_silence_ms
   - `settings_hotkey`: combo, mode
   - `settings_output`: method, paste_delay_ms, add_trailing_space
   - `settings_postprocess`: fix_punctuation, capitalize_sentences, remove_fillers, format_numbers, fix_unicode, handle_self_corrections
   - `settings_llm`: enabled, model, system_prompt, prompt, trigger_phrase, auto_on_length_enabled, auto_on_length_threshold
   - `settings_general`: history_enabled, active_profile
3. **Interactive Control & Validation**: `ui/pages/settings-page.slint` displays these settings grouped into 7 accordion panels. It uses standard text fields, custom animated `ToggleSwitch` widgets, Slint sliders, and Dropdown ComboBoxes. Sensitive credentials (like `openai_api_key`) are dynamically masked when inactive.
4. **Asynchronous Saving (PATCH)**: Saving is granular and atomic per section. Clicking "Save" on a section accordion triggers a corresponding Slint callback:
   - The UI marshals the respective Slint properties into a Python dictionary.
   - It spawns a background thread that executes a `PATCH /settings/{section}` HTTP request containing the section data (or falls back to direct configuration writing using `backend.config.write_config(section, data)`).
   - The backend validates the section name, writes the new values to `~/.config/carefulwhisper/config.toml`, and returns success.
   - Upon a successful update, the UI thread triggers a floating `Snackbar` notification overlay that auto-dismisses after 2.5 seconds using a thread-safe `Timer`.
5. **Configuration Reset**: Clicking "Reset to Defaults" fires a `POST /settings/reset` request to the daemon (with a direct `backend.config.write_default_config()` fallback) which overwrites the active configuration with clean defaults. The UI thread then automatically re-fetches the values from the backend and re-binds them to refresh all settings panels instantly.

