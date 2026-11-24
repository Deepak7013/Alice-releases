"""Deterministic capability-to-tool resolution for governed execution.

Resolution is advisory only: it selects candidates and never grants permission or
executes a tool. A candidate must satisfy both the capability registry state and the
governed tool contract before it can be selected.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Resolution:
    selected: str | None
    allowed: bool
    reason: str
    candidates: tuple[str, ...] = ()


class CapabilityToolResolver:
    """Match requested capabilities to verified, governed tools."""

    def resolve(self, capability: dict, tools: list[dict]) -> Resolution:
        if not capability or not capability.get("name"):
            return Resolution(None, False, "missing_capability")
        if not capability.get("enabled", True) or not capability.get("configured", True):
            return Resolution(None, False, "capability_not_ready")
        if capability.get("status") not in {"available", "degraded"}:
            return Resolution(None, False, "capability_not_available")
        if not capability.get("verified", False):
            return Resolution(None, False, "capability_not_verified")

        wanted = str(capability["name"]).strip().lower()
        ranked = []
        for tool in tools or []:
            name = str(tool.get("name", "")).strip()
            caps = {str(x).strip().lower() for x in tool.get("capabilities", ())}
            if not name or wanted not in caps:
                continue
            if not tool.get("verified", False):
                continue
            risk = str(tool.get("risk", ""))
            if risk not in {"read", "write", "execute", "external"}:
                continue
            if risk != "read" and not tool.get("permissions"):
                continue
            ranked.append(name)

        candidates = tuple(sorted(set(ranked)))
        if not candidates:
            return Resolution(None, False, "no_governed_tool", ())
        return Resolution(candidates[0], True, "tool_selected", candidates)
