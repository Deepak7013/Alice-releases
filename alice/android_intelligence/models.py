from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class AndroidDevice:
    serial: str
    state: str = "unknown"
    model: str = ""
    android_version: str = ""

@dataclass(frozen=True)
class AndroidElement:
    text: str = ""
    hint: str = ""
    content_desc: str = ""
    resource_id: str = ""
    class_name: str = ""
    clickable: bool = False
    enabled: bool = True
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    index: int = 0
    focused: bool = False

    @property
    def label(self) -> str:
        return self.text or self.content_desc or self.resource_id.rsplit("/", 1)[-1]

@dataclass
class AndroidScreenState:
    serial: str
    package: str = ""
    activity: str = ""
    elements: list[AndroidElement] = field(default_factory=list)
    fingerprint: str = ""
    screenshot_path: str | None = None

    def find(self, query: str, role: str | None = None) -> AndroidElement | None:
        q = query.strip().lower()
        candidates = self.elements
        if role:
            roleq = role.lower()
            candidates = [e for e in candidates if roleq in e.class_name.lower() or (roleq == "button" and e.clickable)]
        for e in candidates:
            if e.label.lower() == q or e.resource_id.lower() == q:
                return e
        for e in candidates:
            if q and q in e.label.lower():
                return e
        return None

@dataclass
class AndroidActionResult:
    ok: bool
    action: str
    message: str = ""
    data: Any = None
