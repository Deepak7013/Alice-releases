"""Screen-state grounding and lightweight change detection."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Callable

DEFAULT_SCREEN_PATH = Path("data/workspace/grounded_screen.png")


class ScreenGrounder:
    """Capture a screen and compare it with the previous observation.

    ``capture`` accepts an optional screenshot function for dependency
    injection/testing, but the normal Alice tool call can simply provide a
    ``path`` (or no arguments at all).
    """

    def __init__(self):
        self.last_hash: str | None = None
        self.last_path: str | None = None

    def capture(
        self,
        screenshot_fn: Callable | str | Path | None = None,
        path: str | Path = DEFAULT_SCREEN_PATH,
    ):
        # Backward compatibility: callers that historically passed the path as
        # the first positional argument should still work.
        if screenshot_fn is None or isinstance(screenshot_fn, (str, Path)):
            if isinstance(screenshot_fn, (str, Path)):
                path = screenshot_fn
            from .screen import screenshot
            screenshot_fn = screenshot

        result = screenshot_fn(str(path))
        if not isinstance(result, dict) or not result.get("ok"):
            return result if isinstance(result, dict) else {
                "ok": False,
                "error": "screenshot function returned an invalid result",
            }

        captured_path = Path(result.get("path", path))
        if not captured_path.exists():
            return {**result, "ok": False, "error": "screenshot file was not created"}

        data = captured_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        changed = self.last_hash is not None and digest != self.last_hash
        self.last_hash = digest
        self.last_path = str(captured_path.resolve())
        return {**result, "hash": digest, "changed": changed}

    def state(self):
        return {
            "path": self.last_path,
            "hash": self.last_hash,
            "timestamp": time.time(),
        }
