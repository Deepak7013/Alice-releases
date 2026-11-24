from __future__ import annotations
from .models import AndroidScreenState, AndroidActionResult

class AndroidSemanticSession:
    def __init__(self, controller, serial: str, max_retries=2):
        self.controller = controller
        self.serial = serial
        self.max_retries = int(max_retries)
        self.state: AndroidScreenState | None = None

    def observe(self):
        self.state = self.controller.observe(self.serial)
        return self.state

    def click(self, query: str, role: str | None = None):
        state = self.state or self.observe()
        element = state.find(query, role)
        if not element:
            state = self.observe()
            element = state.find(query, role)
        if not element or not element.enabled:
            return AndroidActionResult(False, "click", f"UI element not found or disabled: {query}")
        result = self.controller.click(self.serial, element)
        self.state = None if result.ok else state
        return result

    def launch(self, package: str):
        result = self.controller.launch(self.serial, package)
        self.state = None
        return result

    def press(self, key: str):
        result = self.controller.press(self.serial, key)
        self.state = None
        return result
