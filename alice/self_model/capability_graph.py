"""Dependency-aware capability readiness for ALICE.

Advisory only: readiness never grants permissions or executes anything.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class CapabilityReadiness:
    name: str
    ready: bool
    reason: str
    missing: tuple[str, ...] = ()
    degraded: tuple[str, ...] = ()

class CapabilityGraph:
    def __init__(self, capability_manager):
        self.manager = capability_manager

    def _status(self, name: str):
        return self.manager.status(name)

    def readiness(self, name: str) -> CapabilityReadiness:
        name = str(name).strip().lower().replace(" ", "_")
        seen=set(); missing=[]; degraded=[]
        def walk(n):
            if n in seen: return
            seen.add(n)
            s=self._status(n)
            if not s.get("known"):
                missing.append(n); return
            if not s.get("enabled") or not s.get("configured"):
                missing.append(n); return
            if s.get("status") != "available" or not s.get("verified"):
                degraded.append(n)
            for dep in s.get("dependencies", []): walk(dep)
        walk(name)
        if missing:
            return CapabilityReadiness(name, False, "missing_dependency", tuple(sorted(set(missing))), tuple(sorted(set(degraded))))
        if degraded:
            return CapabilityReadiness(name, False, "dependency_not_verified_or_degraded", (), tuple(sorted(set(degraded))))
        return CapabilityReadiness(name, True, "ready")

    def explain(self, name: str) -> dict:
        return asdict(self.readiness(name))
