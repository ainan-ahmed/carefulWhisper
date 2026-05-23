import threading
import os
import pystray
from PIL import Image, ImageDraw

_icon = None
_state_lock = threading.Lock()
_cached_images = {}

def _pre_render_images():
    global _cached_images
    states = {
        "idle": (100, 100, 100),
        "working": (50, 150, 255),
        "done": (50, 255, 50)
    }
    for state, color in states.items():
        image = Image.new('RGB', (64, 64), color=(30, 30, 30))
        dc = ImageDraw.Draw(image)
        dc.ellipse((16, 16, 48, 48), fill=color)
        _cached_images[state] = image

def set_state(state: str):
    global _icon
    with _state_lock:
        if _icon and state in _cached_images:
            _icon.icon = _cached_images[state]

def revert_idle_later():
    """Helper to revert to idle after a delay, typically called after 'done'."""
    threading.Timer(2.0, lambda: set_state("idle")).start()

def on_open_ui(icon, item):
    print("Tray: Open Slint UI clicked (Coming Soon)")

def on_quit(icon, item):
    print("Tray: Quit clicked")
    icon.stop()
    import signal
    os.kill(os.getpid(), signal.SIGINT)

def run_tray():
    global _icon
    _pre_render_images()
    _icon = pystray.Icon("carefulWhisper")
    _icon.menu = pystray.Menu(
        pystray.MenuItem("Open Slint UI", on_open_ui),
        pystray.MenuItem("Quit", on_quit)
    )
    _icon.icon = _cached_images["idle"]
    _icon.title = "carefulWhisper"
    
    # Run blocks the main thread
    _icon.run()
