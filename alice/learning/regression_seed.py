"""Convert verified failure observations into deterministic regression seeds."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib

@dataclass(frozen=True)
class RegressionSeed:
    fingerprint: str
    scenario: str
    expected: str
    reason: str

class RegressionSeedGenerator:
    def create(self, *, scenario: str, expected: str, reason: str, verified_failure: bool) -> dict:
        if not verified_failure:
            return {"created":False,"reason":"verified_failure_required"}
        scenario=str(scenario).strip(); expected=str(expected).strip(); reason=str(reason).strip()
        if not scenario or not expected:
            return {"created":False,"reason":"scenario_and_expected_required"}
        fp=hashlib.sha256((scenario+'\n'+expected+'\n'+reason).encode()).hexdigest()[:16]
        seed=RegressionSeed(fp,scenario[:1000],expected[:1000],reason[:500])
        return {"created":True,"seed":asdict(seed)}
