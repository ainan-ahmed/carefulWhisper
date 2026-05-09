"""
Text output — types transcribed text at the current cursor position.
Auto-detects X11 vs Wayland and picks the best method.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time

from backend.config import OutputConfig

logger = logging.getLogger("carefulwhisper.output")


def _ydotool_ready() -> bool:
    """Return True only if ydotool binary exists AND ydotoold daemon is running."""
    import os

    if not shutil.which("ydotool"):
        return False
    uid = os.getuid()
    socket = os.environ.get("YDOTOOL_SOCKET", f"/run/user/{uid}/.ydotool_socket")
    if not os.path.exists(socket):
        logger.warning(
            "ydotool found but daemon socket %s missing — run: ydotoold &", socket
        )
        return False
    return True


def _detect_method() -> str:
    """Detect the best output method for the current session."""
    import os

    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session == "wayland" or (
        not shutil.which("xdotool") and shutil.which("ydotool")
    ):
        if _ydotool_ready():
            return "ydotool"
        logger.warning(
            "Wayland detected but ydotool unavailable — falling back to clipboard"
        )
        return "clipboard"
    if shutil.which("xdotool"):
        return "xdotool"
    logger.warning("xdotool not found — falling back to clipboard")
    return "clipboard"


class TextOutput:
    def __init__(self, cfg: OutputConfig) -> None:
        self.cfg = cfg
        self._method = cfg.method if cfg.method != "auto" else _detect_method()
        logger.info("Output method: %s", self._method)

    def paste(self, text: str) -> None:
        if self.cfg.add_trailing_space:
            text = text + " "

        time.sleep(self.cfg.paste_delay_ms / 1000)

        match self._method:
            case "xdotool":
                self._xdotool_type(text)
            case "ydotool":
                self._ydotool_type(text)
            case "clipboard":
                self._clipboard_paste(text)
            case _:
                logger.error("Unknown output method: %s", self._method)

    def _xdotool_type(self, text: str) -> None:
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
            check=True,
        )

    def _ydotool_type(self, text: str) -> None:
        result = subprocess.run(["ydotool", "type", "--", text])
        if result.returncode != 0:
            logger.error(
                "ydotool type failed (exit %d) — is ydotoold running? Run: ydotoold &",
                result.returncode,
            )

    def _clipboard_paste(self, text: str) -> None:
        import pyperclip  # type: ignore[import]

        prev = pyperclip.paste()
        pyperclip.copy(text)
        time.sleep(0.05)
        # Simulate Ctrl+V with whichever tool is available
        if _ydotool_ready():
            subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"])
        elif shutil.which("xdotool"):
            subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"])
        else:
            logger.error("Cannot simulate Ctrl+V — install xdotool or ydotool")
        time.sleep(0.05)
        pyperclip.copy(prev)  # restore clipboard
