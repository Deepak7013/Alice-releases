
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class UIElement:
    id: str
    role: str
    name: str
    bounds: tuple[int, int, int, int] | None = None
    enabled: bool = True
    visible: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class ScreenState:
    platform: str
    title: str = ""
    app: str = ""
    elements: list[UIElement] = field(default_factory=list)
    fingerprint: str = ""

    def find(self, name: str, role: str | None = None) -> UIElement | None:
        q = name.casefold()
        for e in self.elements:
            if e.visible and e.enabled and e.name.casefold() == q:
                if role is None or e.role == role:
                    return e
        return None

@dataclass
class ActionResult:
    ok: bool
    action: str
    message: str = ""
    state_changed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
