
from __future__ import annotations
import subprocess, hashlib
from .models import UIElement, ScreenState, ActionResult

class AndroidController:
    platform = "android"

    def __init__(self, serial: str | None = None, runner=None):
        self.serial = serial
        self.runner = runner or self._run

    def _run(self, args):
        cmd = ["adb"]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += args
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15)

    def devices(self) -> list[str]:
        r = self.runner(["devices"])
        if r.returncode != 0:
            return []
        return [line.split()[0] for line in r.stdout.splitlines()
                if line.strip() and not line.startswith("List of") and
                len(line.split()) >= 2 and line.split()[1] == "device"]

    def shell(self, *args: str) -> ActionResult:
        r = self.runner(["shell", *args])
        return ActionResult(r.returncode == 0, "android_shell",
                            r.stdout.strip() or r.stderr.strip())

    def tap(self, x: int, y: int) -> ActionResult:
        r = self.runner(["shell", "input", "tap", str(x), str(y)])
        return ActionResult(r.returncode == 0, "tap", f"{x},{y}", True)

    def swipe(self, x1, y1, x2, y2, duration=300) -> ActionResult:
        r = self.runner(["shell", "input", "swipe",
                         str(x1), str(y1), str(x2), str(y2), str(duration)])
        return ActionResult(r.returncode == 0, "swipe", "", True)

    def type_text(self, text: str) -> ActionResult:
        safe = text.replace(" ", "%s")
        r = self.runner(["shell", "input", "text", safe])
        return ActionResult(r.returncode == 0, "type", "", True)
