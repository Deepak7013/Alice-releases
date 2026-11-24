
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class VisualTarget:
    name: str
    role: str | None = None
    confidence: float = 0.0
    bounds: tuple[int, int, int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class VisualFrame:
    platform: str
    image_path: str | None = None
    fingerprint: str = ""
    width: int = 0
    height: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class VisualObservation:
    frame: VisualFrame
    targets: list[VisualTarget] = field(default_factory=list)
    text: str = ""
    confidence: float = 0.0

    def find(self, name: str, role: str | None = None) -> VisualTarget | None:
        q = name.casefold()
        candidates = [
            t for t in self.targets
            if t.name.casefold() == q
            and (role is None or t.role == role)
        ]
        return max(candidates, key=lambda x: x.confidence, default=None)
