from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class WorkspaceProject:
    """Persistent metadata for one Alice-managed personal project."""
    project_id: str
    name: str
    description: str = ""
    status: str = "active"
    tags: List[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class WorkspaceDocument:
    """Metadata describing a file stored inside a workspace project."""
    project_id: str
    path: str
    size: int
    modified_at: float
    kind: str = "text"


@dataclass
class WorkspaceSearchResult:
    project_id: str
    path: str
    line: int
    text: str
