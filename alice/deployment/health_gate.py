from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class HealthGateResult:
    tests_ok: bool
    manifest_ok: bool
    version_ok: bool
    protected_ok: bool
    healthy: bool
    def as_dict(self): return asdict(self)

def evaluate_health(tests_ok, manifest_ok, version_ok, protected_ok=True):
    vals = (bool(tests_ok), bool(manifest_ok), bool(version_ok), bool(protected_ok))
    return HealthGateResult(*vals, all(vals))
