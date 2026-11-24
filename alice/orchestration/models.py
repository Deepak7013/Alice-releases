from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class ResourceKind(str, Enum):
    PC = "pc"
    ANDROID = "android"
    BROWSER = "browser"
    FILES = "files"
    VOICE = "voice"
    AI = "ai"

@dataclass(frozen=True)
class Resource:
    resource_id: str
    kind: ResourceKind | str
    name: str = ""
    capabilities: tuple[str, ...] = ()
    online: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class RouteStep:
    resource_id: str
    capability: str
    action: str = ""
    depends_on: tuple[int, ...] = ()

@dataclass
class OrchestrationPlan:
    goal: str
    steps: list[RouteStep] = field(default_factory=list)
    rationale: str = ""
    requires_confirmation: bool = False

@dataclass
class OrchestrationResult:
    ok: bool
    goal: str
    completed_steps: list[dict[str, Any]] = field(default_factory=list)
    failed_step: int | None = None
    error: str = ""
    synchronized: bool = True
