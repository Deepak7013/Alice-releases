
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class BrowserElement:
    role: str
    name: str = ""
    selector: str | None = None
    value: str | None = None
    visible: bool = True
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class FormField:
    label: str
    field_type: str = "text"
    selector: str | None = None
    required: bool = False
    value: str | None = None

@dataclass
class BrowserTab:
    id: str
    url: str
    title: str = ""
    active: bool = False

@dataclass
class BrowserPageState:
    url: str
    title: str = ""
    elements: list[BrowserElement] = field(default_factory=list)
    forms: list[FormField] = field(default_factory=list)
    logged_in: bool | None = None
    structure_quality: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
