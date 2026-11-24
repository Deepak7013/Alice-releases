from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

class ArtifactKind(str, Enum):
    TEXT = "text"
    CODE = "code"
    MARKDOWN = "markdown"
    DIAGRAM = "diagram"
    IMAGE = "image"
    AI_AGENT = "ai_agent"
    PROJECT = "project"

@dataclass
class CreationRequest:
    prompt: str
    kind: ArtifactKind = ArtifactKind.TEXT
    filename: str | None = None
    project_name: str | None = None
    style: str = "clear"
    context: dict[str, Any] = field(default_factory=dict)

@dataclass
class Artifact:
    kind: ArtifactKind
    path: str
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def exists(self) -> bool:
        return Path(self.path).exists()
