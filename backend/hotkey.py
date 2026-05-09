"""
Global hotkey manager.

Uses pynput for non-Wayland environments.
Uses evdev on Linux Wayland where pynput global hotkeys are unreliable.
"""

from __future__ import annotations

import logging
import os
import platform
import select
import threading
from typing import Any, Callable

from backend.config import HotkeyConfig

logger = logging.getLogger("carefulwhisper.hotkey")

RecordStartCb = Callable[[], None]
RecordStopCb = Callable[[], None]


class HotkeyManager:
    def __init__(self, cfg: HotkeyConfig) -> None:
        self.cfg = cfg
        self._on_start: RecordStartCb | None = None
        self._on_stop: RecordStopCb | None = None
        self._hotkey: object = None
        self._toggled = False  # for toggle mode

        # evdev state (Wayland/Linux)
        self._evdev_thread: threading.Thread | None = None
        self._evdev_stop_event = threading.Event()
        self._evdev_devices: list[object] = []
        self._evdev_required_groups: list[set[int]] = []
        self._evdev_tracked_codes: set[int] = set()
        self._evdev_pressed_codes: set[int] = set()
        self._evdev_combo_active = False
        self._evdev_mode = "hold"
        self._running = False

    def register(self, on_start: RecordStartCb, on_stop: RecordStopCb) -> None:
        self._on_start = on_start
        self._on_stop = on_stop

    def start(self) -> None:
        if self._running:
            logger.debug("Hotkey listener already running; ignoring start()")
            return

        mode = self.cfg.mode
        combo = self.cfg.combo
        self._toggled = False

        if mode == "always_on":
            logger.info("Always-on mode — starting immediately")
            if self._on_start:
                self._on_start()
            self._running = True
            return

        if mode not in {"hold", "toggle"}:
            raise ValueError(f"Unknown hotkey mode: {mode!r}")

        if self._should_use_evdev() and self._start_evdev_listener(combo, mode):
            self._running = True
            logger.info("Using evdev hotkey backend")
            return

        if mode == "hold":
            self._start_hold_listener(combo)
        else:
            self._start_toggle_listener(combo)
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return

        self._stop_evdev_listener()
        if self._hotkey:
            self._hotkey.stop()  # type: ignore[attr-defined]
            self._hotkey = None
        self._running = False

    # ── Backend detection ─────────────────────────────────────────────────────

    def _should_use_evdev(self) -> bool:
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        return platform.system() == "Linux" and session == "wayland"

    # ── pynput backend ────────────────────────────────────────────────────────

    def _start_hold_listener(self, combo: str) -> None:
        from pynput import keyboard  # type: ignore[import]

        hotkey = keyboard.HotKey(
            keyboard.HotKey.parse(combo),
            on_activate=self._hold_activate,
        )

        def on_press(key: object) -> None:
            hotkey.press(listener.canonical(key))  # type: ignore[arg-type]

        def on_release(key: object) -> None:
            canonical = listener.canonical(key)  # type: ignore[arg-type]
            hotkey.release(canonical)
            try:
                parsed = keyboard.HotKey.parse(combo)
                if canonical in parsed:
                    self._hold_deactivate()
            except Exception:
                pass

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._hotkey = listener
        listener.start()
        logger.info("Hold-to-record hotkey active via pynput: %s", combo)

    def _start_toggle_listener(self, combo: str) -> None:
        from pynput import keyboard  # type: ignore[import]

        def on_activate() -> None:
            self._toggled = not self._toggled
            if self._toggled:
                logger.debug("Toggle: start")
                if self._on_start:
                    self._on_start()
            else:
                logger.debug("Toggle: stop")
                if self._on_stop:
                    self._on_stop()

        hotkey = keyboard.GlobalHotKeys({combo: on_activate})
        self._hotkey = hotkey
        hotkey.start()
        logger.info("Toggle hotkey active via pynput: %s", combo)

    # ── evdev backend ─────────────────────────────────────────────────────────

    def _start_evdev_listener(self, combo: str, mode: str) -> bool:
        try:
            import evdev
            from evdev import ecodes
        except ImportError:
            logger.warning(
                "Wayland detected but evdev not installed; falling back to pynput"
            )
            return False

        required_groups = self._parse_evdev_combo(combo, ecodes)
        if not required_groups:
            logger.error("Could not parse hotkey combo for evdev: %s", combo)
            return False

        tracked_codes = set().union(*required_groups)

        try:
            devices = self._open_keyboard_devices(evdev, ecodes)
        except PermissionError:
            logger.error(
                "No permission to read keyboard devices under /dev/input; "
                "falling back to pynput"
            )
            return False

        if not devices:
            logger.warning("No keyboard input devices found for evdev backend")
            return False

        self._evdev_required_groups = required_groups
        self._evdev_tracked_codes = tracked_codes
        self._evdev_pressed_codes.clear()
        self._evdev_combo_active = False
        self._evdev_mode = mode
        self._evdev_devices = devices
        self._evdev_stop_event.clear()
        self._evdev_thread = threading.Thread(target=self._evdev_loop, daemon=True)
        self._evdev_thread.start()
        logger.info("%s hotkey active via evdev: %s", mode.capitalize(), combo)
        return True

    def _stop_evdev_listener(self) -> None:
        self._evdev_stop_event.set()
        if self._evdev_thread and self._evdev_thread.is_alive():
            self._evdev_thread.join(timeout=1.5)
        self._evdev_thread = None
        for device in self._evdev_devices:
            try:
                device.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._evdev_devices = []
        self._evdev_required_groups = []
        self._evdev_tracked_codes.clear()
        self._evdev_pressed_codes.clear()
        self._evdev_combo_active = False

    def _open_keyboard_devices(self, evdev: Any, ecodes: Any) -> list[object]:
        devices: list[object] = []
        permission_denied = False

        for path in evdev.list_devices():  # type: ignore[attr-defined]
            try:
                device = evdev.InputDevice(path)  # type: ignore[attr-defined]
            except PermissionError:
                permission_denied = True
                continue
            except Exception:
                continue

            try:
                caps = device.capabilities()
                key_caps = caps.get(ecodes.EV_KEY, [])
                looks_like_keyboard = any(
                    code in key_caps
                    for code in (
                        ecodes.KEY_A,
                        ecodes.KEY_Z,
                        ecodes.KEY_SPACE,
                        ecodes.KEY_ENTER,
                    )
                )
                if looks_like_keyboard:
                    devices.append(device)
                else:
                    device.close()
            except Exception:
                try:
                    device.close()
                except Exception:
                    pass

        if not devices and permission_denied:
            raise PermissionError("Could not open any keyboard input devices")
        return devices

    def _evdev_loop(self) -> None:
        from evdev import ecodes

        while not self._evdev_stop_event.is_set() and self._evdev_devices:
            try:
                ready, _, _ = select.select(self._evdev_devices, [], [], 0.2)
            except Exception:
                break

            for device in ready:
                try:
                    for event in device.read():  # pyright: ignore[reportAttributeAccessIssue]
                        if event.type != ecodes.EV_KEY:
                            continue
                        self._handle_evdev_key_event(event.code, event.value)
                except OSError:
                    continue
                except Exception:
                    logger.exception("Unexpected evdev read error")

    def _handle_evdev_key_event(self, code: int, value: int) -> None:
        if code not in self._evdev_tracked_codes:
            return

        if value in (1, 2):
            self._evdev_pressed_codes.add(code)
        elif value == 0:
            self._evdev_pressed_codes.discard(code)
        else:
            return

        combo_now_active = self._evdev_combo_is_active()

        if self._evdev_mode == "hold":
            if combo_now_active and not self._evdev_combo_active:
                self._evdev_combo_active = True
                self._hold_activate()
            elif not combo_now_active and self._evdev_combo_active:
                self._evdev_combo_active = False
                self._hold_deactivate()
            return

        # toggle mode
        if combo_now_active and not self._evdev_combo_active:
            self._evdev_combo_active = True
            self._toggled = not self._toggled
            if self._toggled:
                logger.debug("Toggle: start")
                if self._on_start:
                    self._on_start()
            else:
                logger.debug("Toggle: stop")
                if self._on_stop:
                    self._on_stop()
        elif not combo_now_active and self._evdev_combo_active:
            self._evdev_combo_active = False

    def _evdev_combo_is_active(self) -> bool:
        return all(
            any(code in self._evdev_pressed_codes for code in group)
            for group in self._evdev_required_groups
        )

    def _parse_evdev_combo(self, combo: str, ecodes: object) -> list[set[int]]:
        groups: list[set[int]] = []
        for raw in combo.split("+"):
            token = raw.strip().lower().removeprefix("<").removesuffix(">")
            if not token:
                continue
            token_codes = self._evdev_codes_for_token(token, ecodes)
            if token_codes is None:
                logger.warning("Unsupported key token for evdev backend: %s", token)
                return []
            groups.append(token_codes)
        return groups

    def _evdev_codes_for_token(self, token: str, ecodes: object) -> set[int] | None:
        alias_groups = {
            "ctrl": ("KEY_LEFTCTRL", "KEY_RIGHTCTRL"),
            "control": ("KEY_LEFTCTRL", "KEY_RIGHTCTRL"),
            "alt": ("KEY_LEFTALT", "KEY_RIGHTALT"),
            "shift": ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"),
            "meta": ("KEY_LEFTMETA", "KEY_RIGHTMETA"),
            "super": ("KEY_LEFTMETA", "KEY_RIGHTMETA"),
            "cmd": ("KEY_LEFTMETA", "KEY_RIGHTMETA"),
            "space": ("KEY_SPACE",),
            "enter": ("KEY_ENTER",),
            "return": ("KEY_ENTER",),
            "tab": ("KEY_TAB",),
            "esc": ("KEY_ESC",),
            "escape": ("KEY_ESC",),
            "backspace": ("KEY_BACKSPACE",),
        }

        key_names = alias_groups.get(token)
        if key_names is None and len(token) == 1 and token.isalpha():
            key_names = (f"KEY_{token.upper()}",)
        elif key_names is None and len(token) == 1 and token.isdigit():
            key_names = (f"KEY_{token}",)
        elif key_names is None:
            key_names = (f"KEY_{token.upper()}",)

        codes = {
            getattr(ecodes, key_name)
            for key_name in key_names
            if hasattr(ecodes, key_name)
        }
        if not codes:
            return None
        return codes

    # ── Shared callbacks ───────────────────────────────────────────────────────

    def _hold_activate(self) -> None:
        logger.debug("Hold: start")
        if self._on_start:
            self._on_start()

    def _hold_deactivate(self) -> None:
        logger.debug("Hold: stop")
        if self._on_stop:
            self._on_stop()
