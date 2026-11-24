from __future__ import annotations
from dataclasses import dataclass
from .models import Resource, ResourceKind

@dataclass
class ResourceGraph:
    """Small local graph of currently usable devices/resources.

    The graph describes availability and capabilities only; it never grants permissions.
    """
    resources: dict[str, Resource]

    def __init__(self):
        self.resources = {}

    def register(self, resource: Resource) -> Resource:
        if not resource.resource_id.strip():
            raise ValueError("resource_id is required")
        self.resources[resource.resource_id] = resource
        return resource

    def unregister(self, resource_id: str) -> bool:
        return self.resources.pop(resource_id, None) is not None

    def get(self, resource_id: str) -> Resource | None:
        return self.resources.get(resource_id)

    def online(self) -> list[Resource]:
        return [r for r in self.resources.values() if r.online]

    def find(self, capability: str, kind: ResourceKind | str | None = None) -> list[Resource]:
        cap = capability.strip().lower()
        kind_value = kind.value if isinstance(kind, ResourceKind) else (kind.lower() if kind else None)
        return [r for r in self.online()
                if cap in {c.lower() for c in r.capabilities}
                and (kind_value is None or str(r.kind).lower().split('.')[-1] == kind_value)]

    def snapshot(self) -> list[dict]:
        return [{"id": r.resource_id, "kind": str(r.kind), "name": r.name,
                 "capabilities": list(r.capabilities), "online": r.online,
                 "metadata": dict(r.metadata)} for r in self.resources.values()]
