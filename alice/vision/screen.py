from pathlib import Path
from datetime import datetime

DEFAULT_SCREEN_PATH = Path("data/workspace/alice_screen.png")


def screenshot(path=None):
    out = Path(path or DEFAULT_SCREEN_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    import pyautogui
    img = pyautogui.screenshot()
    img.save(out)
    return {
        "ok": True,
        "path": str(out.resolve()),
        "time": datetime.now().isoformat(),
        "width": img.width,
        "height": img.height,
    }
