from __future__ import annotations
import subprocess
import xml.etree.ElementTree as ET
from .models import AndroidDevice, AndroidActionResult, AndroidScreenState
from .state import AndroidStateParser

class AndroidIntelligenceController:
    """Semantic Android controller using ADB with explicit device scoping."""
    def __init__(self, adb="adb", runner=None, parser=None):
        self.adb = adb
        self.runner = runner or self._default_runner
        self.parser = parser or AndroidStateParser()

    def _default_runner(self, args, timeout=30):
        # ADB output includes Android UI/activity text. Do not let the Windows
        # console code page crash the reader thread on non-CP1252 characters.
        return subprocess.run([self.adb, *map(str, args)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)

    def _run(self, args, timeout=30):
        p = self.runner(args, timeout)
        if p.returncode:
            raise RuntimeError((p.stderr or p.stdout or "ADB command failed").strip())
        return p

    def devices(self) -> list[AndroidDevice]:
        p = self._run(["devices", "-l"])
        out = []
        for line in p.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                model = next((x.split(":",1)[1] for x in parts[2:] if x.startswith("model:")), "")
                out.append(AndroidDevice(parts[0], parts[1], model=model))
        return out

    def _target(self, serial: str) -> list[str]:
        if not serial or any(c in serial for c in " \t\r\n;|&"):
            raise ValueError("a valid device serial is required")
        return ["-s", serial]

    def shell(self, serial: str, args: list[str], timeout=30):
        if not args or any("\x00" in str(x) for x in args):
            raise ValueError("invalid Android shell arguments")
        return self._run([*self._target(serial), "shell", *map(str, args)], timeout)

    def ui_xml(self, serial: str) -> str:
        # Use stdout directly when a runner provides the dump output. Real adb uses exec-out.
        p = self._run([*self._target(serial), "exec-out", "uiautomator", "dump", "/dev/tty"], timeout=30)
        text = p.stdout
        start = text.find("<hierarchy")
        end = text.rfind("</hierarchy>")
        if start >= 0 and end >= 0:
            return text[start:end+len("</hierarchy>")]
        # Some adb versions write the XML to /sdcard first; support a deterministic fallback.
        self._run([*self._target(serial), "shell", "uiautomator", "dump", "/sdcard/__alice_ui.xml"], timeout=30)
        p = self._run([*self._target(serial), "exec-out", "cat", "/sdcard/__alice_ui.xml"], timeout=30)
        return p.stdout

    def current_activity(self, serial: str) -> tuple[str, str]:
        p = self.shell(serial, ["dumpsys", "activity", "activities"])
        package = activity = ""
        for line in p.stdout.splitlines():
            if ("mResumedActivity:" in line or "ResumedActivity:" in line
                    or "topResumedActivity" in line):
                tail = line.split(":", 1)[-1].strip()
                parts = tail.split()
                for part in parts:
                    if "/" in part and not part.startswith("http"):
                        package, activity = part.split("/", 1)
                        break
                if package:
                    break
        return package, activity

    def observe(self, serial: str) -> AndroidScreenState:
        package, activity = self.current_activity(serial)
        xml = self.ui_xml(serial)
        return self.parser.parse(serial, xml, package, activity)

    def click(self, serial: str, element):
        x1, y1, x2, y2 = element.bounds
        if x2 <= x1 or y2 <= y1:
            return AndroidActionResult(False, "click", "element has no usable bounds")
        p = self.shell(serial, ["input", "tap", (x1+x2)//2, (y1+y2)//2])
        return AndroidActionResult(True, "click", data=p.stdout)

    def tap(self, serial: str, x: int, y: int):
        p = self.shell(serial, ["input", "tap", int(x), int(y)])
        return AndroidActionResult(True, "tap", data=p.stdout)

    def swipe(self, serial: str, x1: int, y1: int, x2: int, y2: int, duration_ms=400):
        p = self.shell(serial, ["input", "swipe", int(x1), int(y1), int(x2), int(y2), int(duration_ms)])
        return AndroidActionResult(True, "swipe", data=p.stdout)

    def press(self, serial: str, key: str):
        allowed = {"HOME", "BACK", "ENTER", "TAB", "ESCAPE", "APP_SWITCH", "POWER"}
        key = str(key).upper()
        if key not in allowed:
            raise ValueError("key is outside the safe Android key allowlist")
        p = self.shell(serial, ["input", "keyevent", key])
        return AndroidActionResult(True, "keyevent", data=p.stdout)

    def launch(self, serial: str, package: str):
        if not package or any(c in package for c in " ;|&\n\r"):
            raise ValueError("invalid Android package")
        p = self.shell(serial, ["monkey", "-p", package, "1"])
        return AndroidActionResult(True, "launch", data=p.stdout)
