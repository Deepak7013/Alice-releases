
from __future__ import annotations
import os, subprocess, hashlib
from .models import UIElement, ScreenState, ActionResult

class WindowsController:
    """Windows adapter. Uses optional native backends when available.

    The public API remains backend-neutral so Alice's planner does not
    depend on PyAutoGUI/UIA implementation details.
    """
    platform = "windows"

    def __init__(self, backend=None):
        self.backend = backend

    def observe(self) -> ScreenState:
        if self.backend and hasattr(self.backend, "observe"):
            return self.backend.observe()
        title = ""
        try:
            import pygetwindow as gw
            active = gw.getActiveWindow()
            title = active.title if active else ""
        except Exception:
            pass
        return ScreenState(platform=self.platform, title=title,
                           fingerprint=hashlib.sha256(title.encode()).hexdigest())

    def launch(self, command: str) -> ActionResult:
        if not command.strip():
            return ActionResult(False, "launch", "empty command")
        try:
            subprocess.Popen(command, shell=False)
            return ActionResult(True, "launch", "process started")
        except Exception as exc:
            return ActionResult(False, "launch", str(exc))

    def click_element(self, element: UIElement) -> ActionResult:
        if not element.bounds:
            return ActionResult(False, "click", "element has no bounds")
        if self.backend and hasattr(self.backend, "click"):
            self.backend.click(element)
            return ActionResult(True, "click", element.name, True)
        try:
            import pyautogui
            x, y, w, h = element.bounds
            pyautogui.click(x + w // 2, y + h // 2)
            return ActionResult(True, "click", element.name, True)
        except Exception as exc:
            return ActionResult(False, "click", str(exc))

    def type_text(self, text: str) -> ActionResult:
        if self.backend and hasattr(self.backend, "type_text"):
            self.backend.type_text(text)
            return ActionResult(True, "type", "text entered", True)
        try:
            import pyautogui
            pyautogui.write(text)
            return ActionResult(True, "type", "text entered", True)
        except Exception as exc:
            return ActionResult(False, "type", str(exc))
