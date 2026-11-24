
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterable
from .models import VisualTarget

@dataclass
class HierarchyNode:
    role: str
    name: str = ""
    bounds: tuple[int, int, int, int] | None = None
    enabled: bool = True
    visible: bool = True
    children: list["HierarchyNode"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

class UIHierarchyAdapter:
    """Normalizes OS/browser accessibility trees into visual targets."""

    def flatten(self, root: HierarchyNode) -> list[HierarchyNode]:
        out = []
        def walk(node):
            out.append(node)
            for child in node.children:
                walk(child)
        walk(root)
        return out

    def targets(self, root: HierarchyNode) -> list[VisualTarget]:
        return [
            VisualTarget(
                name=n.name,
                role=n.role,
                confidence=1.0 if n.name else 0.8,
                bounds=n.bounds,
                metadata={"source": "ui_hierarchy", **n.metadata},
            )
            for n in self.flatten(root)
            if n.visible and n.enabled and (n.name or n.bounds)
        ]
