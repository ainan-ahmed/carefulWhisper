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


class App(slint.loader.ui.app_window.AppWindow):
    """Main application class wiring Slint UI to backend data."""

    def __init__(self):
        super().__init__()
        self._store = HistoryStore()
        self._all_transcripts: list = []
        self._refresh_history()
        self._loop = asyncio.get_event_loop()

        # Start status polling thread
        self._current_status = "idle"
        self._polling_active = True
        self._poll_thread = threading.Thread(target=self._poll_backend_status, daemon=True)
        self._poll_thread.start()

    def _poll_backend_status(self) -> None:
        """Poll backend status endpoint and update UI state safely."""
        while self._polling_active:
            try:
                # Default backend port is 7331
                with urllib.request.urlopen("http://127.0.0.1:7331/transcribe/status", timeout=0.4) as response:
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
            await self._send_post_request("http://127.0.0.1:7331/transcribe/start")
        elif status == "recording":
            logger.info("UI: stop recording requested")
            await self._send_post_request("http://127.0.0.1:7331/transcribe/stop")

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
