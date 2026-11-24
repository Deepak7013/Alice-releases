from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class DeviceState:
    resource_id: str
    revision: int = 0
    state: dict[str, Any] = field(default_factory=dict)

class StateSynchronizer:
    """Tracks lightweight orchestration state; it does not copy secrets or grant access."""
    def __init__(self):
        self._states: dict[str, DeviceState] = {}
        self._global_revision = 0

    def update(self, resource_id: str, state: dict[str, Any]) -> DeviceState:
        self._global_revision += 1
        current = self._states.get(resource_id, DeviceState(resource_id))
        current.revision = self._global_revision
        current.state = dict(state)
        self._states[resource_id] = current
        return current

    def get(self, resource_id: str) -> DeviceState | None:
        return self._states.get(resource_id)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {k: {"revision": v.revision, "state": dict(v.state)} for k, v in self._states.items()}

    def mark_observed(self, resource_id: str, **state: Any) -> DeviceState:
        return self.update(resource_id, state)
