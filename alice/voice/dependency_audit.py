"""Audit voice backend ownership before primary selection."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceDependencyAudit:
    allowed: bool
    provider: str | None
    local_owned: bool
    remote_dependency: bool
    reason: str


class VoiceDependencyAuditGate:
    def evaluate(self, provider: object | None, *, require_local: bool = True) -> VoiceDependencyAudit:
        if provider is None:
            return VoiceDependencyAudit(False, None, False, False, "provider_missing")
        name = str(getattr(provider, "name", provider.__class__.__name__) or "").strip()
        local_owned = bool(getattr(provider, "local_owned", False))
        remote_dependency = bool(getattr(provider, "remote_dependency", not local_owned))
        if require_local and (not local_owned or remote_dependency):
            return VoiceDependencyAudit(False, name, local_owned, remote_dependency, "local_ownership_required")
        if not local_owned and not require_local:
            return VoiceDependencyAudit(True, name, False, remote_dependency, "non_local_allowed_by_policy")
        return VoiceDependencyAudit(True, name, True, False, "local_owned_provider_admitted")
