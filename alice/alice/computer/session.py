
from __future__ import annotations
from dataclasses import dataclass
from .models import ScreenState, ActionResult

@dataclass
class ComputerSession:
    controller: object
    state: ScreenState | None = None
    recovery_attempts: int = 2

    def observe(self) -> ScreenState:
        self.state = self.controller.observe()
        return self.state

    def click(self, name: str, role: str | None = None) -> ActionResult:
        state = self.state or self.observe()
        element = state.find(name, role)
        if not element:
            self.observe()
            element = self.state.find(name, role) if self.state else None
        if not element:
            return ActionResult(False, "click", f"UI element not found: {name}")
        result = self.controller.click_element(element)
        if result.ok:
            self.state = None
        return result

    def type_text(self, text: str) -> ActionResult:
        result = self.controller.type_text(text)
        if result.ok:
            self.state = None
        return result
