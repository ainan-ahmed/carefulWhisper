"""
carefulWhisper Slint UI — standalone desktop window.

Launch:  uv run python -m ui.main
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import pyperclip
import slint

# Ensure the project root is on sys.path so slint.loader can find ui/app-window.slint
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.history import HistoryStore

logger = logging.getLogger("carefulwhisper.ui")

BACKEND_BASE = "http://127.0.0.1:7331"


def _format_timestamp(iso_str: str) -> str:
    """Convert ISO timestamp to human-readable format."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%b %d, %Y · %H:%M")
    except (ValueError, TypeError):
        return iso_str


def _transcripts_to_dicts(transcripts) -> list[dict]:
    """Convert Transcript dataclass instances to dicts for Slint ListModel."""
    items = []
    for t in transcripts:
        items.append({
            "id": t.id,
            "text": t.text,
            "created_at": _format_timestamp(t.created_at),
            "word_count": t.word_count or 0,
            "duration_s": t.duration_s or 0.0,
            "backend": t.backend or "",
        })
    return items


def _http_get_json(path: str) -> dict | None:
    """GET a JSON endpoint from the backend."""
    try:
        with urllib.request.urlopen(f"{BACKEND_BASE}{path}", timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        logger.error("GET %s failed: %s", path, e)
        return None


def _http_patch_json(path: str, data: dict) -> dict | None:
    """PATCH a JSON endpoint on the backend."""
    try:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{BACKEND_BASE}{path}",
            data=payload,
            method="PATCH",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        logger.error("PATCH %s failed: %s", path, e)
        return None


def _http_post(path: str) -> dict | None:
    """POST to a backend endpoint."""
    try:
        req = urllib.request.Request(f"{BACKEND_BASE}{path}", method="POST")
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        logger.error("POST %s failed: %s", path, e)
        return None


class App(slint.loader.ui.app_window.AppWindow):
    """Main application class wiring Slint UI to backend data."""

    def __init__(self):
        super().__init__()
        self._store = HistoryStore()
        self._all_transcripts: list = []
        self._refresh_history()
        self._loop = asyncio.get_event_loop()
        self._snackbar_timer: threading.Timer | None = None

        # Load settings from backend/config
        self._load_settings()

        # Start status polling thread
        self._current_status = "idle"
        self._polling_active = True
        self._poll_thread = threading.Thread(target=self._poll_backend_status, daemon=True)
        self._poll_thread.start()

    # ── Settings loading ──────────────────────────────────────────────────

    def _load_settings(self) -> None:
        """Load all settings from backend API or config directly."""
        data = _http_get_json("/settings/")
        if data is None:
            # Fallback: load directly from config module
            try:
                from backend.config import load_config
                cfg = load_config()
                data = {
                    "stt": vars(cfg.stt),
                    "audio": vars(cfg.audio),
                    "hotkey": vars(cfg.hotkey),
                    "output": vars(cfg.output),
                    "postprocess": vars(cfg.postprocess),
                    "llm": vars(cfg.llm),
                    "active_profile": cfg.active_profile,
                    "history_enabled": cfg.history_enabled,
                }
            except Exception:
                logger.exception("Failed to load settings")
                return

        self._apply_settings(data)

    def _apply_settings(self, data: dict) -> None:
        """Push settings dict into Slint properties."""
        stt = data.get("stt", {})
        self.settings_stt = {
            "backend": stt.get("backend", "faster_whisper"),
            "model": stt.get("model", "base.en"),
            "language": stt.get("language", "en"),
            "device": stt.get("device", "auto"),
            "compute_type": stt.get("compute_type", "int8"),
            "openai_api_key": stt.get("openai_api_key", ""),
            "fallback_to_cloud": stt.get("fallback_to_cloud", False),
        }

        audio = data.get("audio", {})
        self.settings_audio = {
            "sample_rate": audio.get("sample_rate", 16000),
            "channels": audio.get("channels", 1),
            "blocksize": audio.get("blocksize", 1024),
            "vad_enabled": audio.get("vad_enabled", True),
            "vad_threshold": audio.get("vad_threshold", 0.5),
            "vad_min_silence_ms": audio.get("vad_min_silence_ms", 500),
        }

        hotkey = data.get("hotkey", {})
        self.settings_hotkey = {
            "combo": hotkey.get("combo", "<ctrl>+<alt>+space"),
            "mode": hotkey.get("mode", "hold"),
        }

        output = data.get("output", {})
        self.settings_output = {
            "method": output.get("method", "auto"),
            "paste_delay_ms": output.get("paste_delay_ms", 50),
            "add_trailing_space": output.get("add_trailing_space", True),
        }

        pp = data.get("postprocess", {})
        self.settings_postprocess = {
            "fix_punctuation": pp.get("fix_punctuation", True),
            "capitalize_sentences": pp.get("capitalize_sentences", True),
            "remove_fillers": pp.get("remove_fillers", False),
            "format_numbers": pp.get("format_numbers", False),
            "fix_unicode": pp.get("fix_unicode", False),
            "handle_self_corrections": pp.get("handle_self_corrections", False),
        }

        llm = data.get("llm", {})
        self.settings_llm = {
            "enabled": llm.get("enabled", False),
            "model": llm.get("model", "gpt-4o-mini"),
            "system_prompt": llm.get("system_prompt", ""),
            "prompt": llm.get("prompt", ""),
            "trigger_phrase": llm.get("trigger_phrase", "and fix this"),
            "auto_on_length_enabled": llm.get("auto_on_length_enabled", False),
            "auto_on_length_threshold": llm.get("auto_on_length_threshold", 200),
        }

        self.settings_general = {
            "history_enabled": data.get("history_enabled", True),
            "active_profile": data.get("active_profile", "default"),
        }

    # ── Snackbar ──────────────────────────────────────────────────────────

    def _show_snackbar(self, message: str, is_error: bool = False) -> None:
        """Show snackbar and auto-dismiss after 2.5s."""
        # Cancel any existing timer
        if self._snackbar_timer:
            self._snackbar_timer.cancel()

        def set_visible():
            self.snackbar_message = message
            self.snackbar_is_error = is_error
            self.snackbar_visible = True

        self._loop.call_soon_threadsafe(set_visible)

        def dismiss():
            def hide():
                self.snackbar_visible = False
            self._loop.call_soon_threadsafe(hide)

        self._snackbar_timer = threading.Timer(2.5, dismiss)
        self._snackbar_timer.daemon = True
        self._snackbar_timer.start()

    # ── Settings save helpers ─────────────────────────────────────────────

    def _save_section(self, section: str, data: dict, label: str) -> None:
        """Save a config section via PATCH and show snackbar."""
        def do_save():
            result = _http_patch_json(f"/settings/{section}", data)
            if result and result.get("status") == "saved":
                self._show_snackbar(f"{label} settings saved")
                logger.info("Saved %s settings", section)
            else:
                # Fallback: write directly
                try:
                    from backend.config import write_config
                    write_config(section, data)
                    self._show_snackbar(f"{label} settings saved")
                    logger.info("Saved %s settings (direct)", section)
                except Exception:
                    self._show_snackbar(f"Failed to save {label} settings", is_error=True)
                    logger.exception("Failed to save %s settings", section)

        threading.Thread(target=do_save, daemon=True).start()

    # ── Status polling ────────────────────────────────────────────────────

    def _poll_backend_status(self) -> None:
        """Poll backend status endpoint and update UI state safely."""
        while self._polling_active:
            try:
                # Default backend port is 7331
                with urllib.request.urlopen(f"{BACKEND_BASE}/transcribe/status", timeout=0.4) as response:
                    data = json.loads(response.read().decode())
                    status = data.get("status", "idle")
            except Exception:
                status = "idle"

            if status != self._current_status:
                old_status = self._current_status
                self._current_status = status

                def update_ui():
                    self.recording_status = status
                    # On finishing transcribing/recording, refresh list automatically
                    if old_status in ("recording", "transcribing") and status == "idle":
                        logger.info("Transcription completed! Auto-refreshing history.")
                        self._refresh_history()

                self._loop.call_soon_threadsafe(update_ui)

            time.sleep(0.25)

    def _refresh_history(self, search: str = "") -> None:
        """Reload transcripts from the database and update the UI model."""
        transcripts = self._store.list(limit=200, search=search)
        self._all_transcripts = transcripts
        items = _transcripts_to_dicts(transcripts)
        self.history = slint.ListModel(items)
        self.total_count = len(items)

    def _find_transcript_text(self, transcript_id: int) -> str | None:
        """Look up the full text for a transcript by ID."""
        for t in self._all_transcripts:
            if t.id == transcript_id:
                return t.text
        return None

    @slint.callback
    def search_changed(self, query: str) -> None:
        """Called when the user types in the search bar."""
        self._refresh_history(search=query.strip())

    @slint.callback
    def copy_transcript(self, transcript_id: int) -> None:
        """Copy the full transcript text to the system clipboard."""
        text = self._find_transcript_text(transcript_id)
        if text:
            try:
                pyperclip.copy(text)
                logger.info("Copied transcript %d to clipboard", transcript_id)
            except Exception:
                logger.exception("Failed to copy to clipboard")

    @slint.callback
    def confirm_delete(self, transcript_id: int) -> None:
        """Delete a transcript after user confirmed via the dialog."""
        deleted = self._store.delete(transcript_id)
        if deleted:
            logger.info("Deleted transcript %d", transcript_id)
        else:
            logger.warning("Transcript %d not found for deletion", transcript_id)
        # Refresh the list
        self._refresh_history()

    @slint.callback
    async def toggle_recording(self) -> None:
        """Handle click on home page microphone icon to toggle recording."""
        status = self.recording_status
        if status == "idle":
            logger.info("UI: start recording requested")
            await self._send_post_request(f"{BACKEND_BASE}/transcribe/start")
        elif status == "recording":
            logger.info("UI: stop recording requested")
            await self._send_post_request(f"{BACKEND_BASE}/transcribe/stop")

    async def _send_post_request(self, url: str) -> None:
        """Send a POST request in a background thread to prevent UI blocking."""
        def send():
            try:
                req = urllib.request.Request(url, method="POST")
                with urllib.request.urlopen(req, timeout=1.5) as r:
                    r.read()
            except Exception as e:
                logger.error(f"UI: network POST to {url} failed: {e}")

        await asyncio.to_thread(send)

    # ── Settings save callbacks ───────────────────────────────────────────

    @slint.callback
    def save_stt_settings(self, stt) -> None:
        """Save STT settings section."""
        data = {
            "backend": str(stt.backend),
            "model": str(stt.model),
            "language": str(stt.language),
            "device": str(stt.device),
            "compute_type": str(stt.compute_type),
            "openai_api_key": str(stt.openai_api_key),
            "fallback_to_cloud": bool(stt.fallback_to_cloud),
        }
        self._save_section("stt", data, "Speech-to-Text")

    @slint.callback
    def save_audio_settings(self, audio) -> None:
        """Save Audio settings section."""
        data = {
            "sample_rate": int(audio.sample_rate),
            "channels": int(audio.channels),
            "blocksize": int(audio.blocksize),
            "vad_enabled": bool(audio.vad_enabled),
            "vad_threshold": float(audio.vad_threshold),
            "vad_min_silence_ms": int(audio.vad_min_silence_ms),
        }
        self._save_section("audio", data, "Audio")

    @slint.callback
    def save_hotkey_settings(self, hotkey) -> None:
        """Save Hotkey settings section."""
        data = {
            "combo": str(hotkey.combo),
            "mode": str(hotkey.mode),
        }
        self._save_section("hotkey", data, "Hotkey")

    @slint.callback
    def save_output_settings(self, output) -> None:
        """Save Output settings section."""
        data = {
            "method": str(output.method),
            "paste_delay_ms": int(output.paste_delay_ms),
            "add_trailing_space": bool(output.add_trailing_space),
        }
        self._save_section("output", data, "Output")

    @slint.callback
    def save_postprocess_settings(self, pp) -> None:
        """Save Postprocess settings section."""
        data = {
            "fix_punctuation": bool(pp.fix_punctuation),
            "capitalize_sentences": bool(pp.capitalize_sentences),
            "remove_fillers": bool(pp.remove_fillers),
            "format_numbers": bool(pp.format_numbers),
            "fix_unicode": bool(pp.fix_unicode),
            "handle_self_corrections": bool(pp.handle_self_corrections),
        }
        self._save_section("postprocess", data, "Post-Processing")

    @slint.callback
    def save_llm_settings(self, llm) -> None:
        """Save LLM settings section."""
        data = {
            "enabled": bool(llm.enabled),
            "model": str(llm.model),
            "system_prompt": str(llm.system_prompt),
            "prompt": str(llm.prompt),
            "trigger_phrase": str(llm.trigger_phrase),
            "auto_on_length_enabled": bool(llm.auto_on_length_enabled),
            "auto_on_length_threshold": int(llm.auto_on_length_threshold),
        }
        self._save_section("llm", data, "LLM")

    @slint.callback
    def save_general_settings(self, general) -> None:
        """Save General settings section."""
        data = {
            "history_enabled": bool(general.history_enabled),
            "active_profile": str(general.active_profile),
        }
        self._save_section("general", data, "General")

    @slint.callback
    def reset_all_settings(self) -> None:
        """Reset all settings to defaults."""
        def do_reset():
            result = _http_post("/settings/reset")
            if result and result.get("status") == "reset":
                self._show_snackbar("All settings reset to defaults")
                # Reload settings
                def reload():
                    self._load_settings()
                self._loop.call_soon_threadsafe(reload)
            else:
                # Fallback: direct reset
                try:
                    from backend.config import write_default_config
                    write_default_config()
                    self._show_snackbar("All settings reset to defaults")
                    def reload():
                        self._load_settings()
                    self._loop.call_soon_threadsafe(reload)
                except Exception:
                    self._show_snackbar("Failed to reset settings", is_error=True)
                    logger.exception("Failed to reset settings")

        threading.Thread(target=do_reset, daemon=True).start()


async def run_app():
    app = App()
    app.show()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("Starting carefulWhisper UI")
    slint.run_event_loop(run_app())


if __name__ == "__main__":
    main()
