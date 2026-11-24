from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import time

class MediaKind(str, Enum):
    IMAGE = "image"
    SCREENSHOT = "screenshot"
    PDF = "pdf"
    DOCUMENT = "document"
    TEXT = "text"
    SVG = "svg"
    UNKNOWN = "unknown"

@dataclass
class MediaEvidence:
    path: str
    kind: MediaKind
    mime_type: str = ""
    size_bytes: int = 0
    pages: int | None = None
    content_hash: str = ""

@dataclass
class VisualElement:
    label: str
    kind: str = "unknown"
    confidence: float = 0.0
    bounds: list[float] | None = None
    text: str = ""

@dataclass
class MultimodalObservation:
    id: str
    evidence: MediaEvidence
    summary: str = ""
    extracted_text: str = ""
    elements: list[VisualElement] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider: str = "local"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
