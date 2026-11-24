"""Local-first governance for ALICE self-engineering.

The governor decides whether self-engineering may use a local model, a remote
fallback, or neither.  It is deliberately deterministic and side-effect free:
it cannot grant permissions, execute code, modify files, or bypass approval.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import os
import time
from pathlib import Path
import json


@dataclass(frozen=True)
class EngineeringRoute:
    mode: str
    local_ready: bool
    local_model: str
    remote_fallback_allowed: bool
    reason: str


class LocalEngineeringGovernor:
    """Policy boundary for the self-engineering reasoning provider."""

    def __init__(self, root=None, status_provider=None):
        self.root = Path(root or Path.cwd()).resolve()
        self.audit_path = self.root / "alice_workspace" / "engineering" / "routing_audit.jsonl"
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_provider = status_provider

    @staticmethod
    def _bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def route(self, local_status=None, *, local_first=None, require_local=None, remote_fallback_allowed=None) -> EngineeringRoute:
        local_status = local_status or (self.status_provider() if self.status_provider else {})
        ready = bool(local_status.get("reachable") and local_status.get("model_available"))
        model = str(local_status.get("model") or os.getenv("LOCAL_AI_MODEL", ""))
        local_first = self._bool("ALICE_SELF_ENGINEER_LOCAL_FIRST", True) if local_first is None else bool(local_first)
        require_local = self._bool("ALICE_SELF_ENGINEER_REQUIRE_LOCAL", False) if require_local is None else bool(require_local)
        remote_allowed = self._bool("ALICE_SELF_ENGINEER_ALLOW_REMOTE_FALLBACK", True) if remote_fallback_allowed is None else bool(remote_fallback_allowed)

        if require_local:
            if ready:
                return EngineeringRoute("local_required", True, model, False, "local model is ready and local-only mode is enabled")
            return EngineeringRoute("blocked", False, model, False, "local-only mode is enabled but the configured local model is unavailable")
        if local_first and ready:
            return EngineeringRoute("local", True, model, remote_allowed, "local model is ready and local-first mode is enabled")
        if remote_allowed:
            return EngineeringRoute("remote_fallback", ready, model, True, "local model is unavailable or local-first mode is disabled")
        return EngineeringRoute("blocked", ready, model, False, "no permitted self-engineering reasoning provider is available")

    def record(self, route: EngineeringRoute, *, outcome="selected"):
        """Persist non-secret routing evidence for diagnostics."""
        row = {"time": time.time(), "outcome": str(outcome)[:120], **asdict(route)}
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row
