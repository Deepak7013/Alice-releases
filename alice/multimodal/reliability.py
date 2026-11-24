from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvidenceAssessment:
    """Deterministic trust/quality assessment for multimodal evidence.

    This does not decide whether an action is safe. It only tells higher layers
    whether the evidence is fresh, intact, complete enough, and suspicious.
    """
    ok: bool
    content_hash: str
    size_bytes: int
    age_seconds: float
    stale: bool
    suspicious: bool
    confidence: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "age_seconds": round(self.age_seconds, 3),
            "stale": self.stale,
            "suspicious": self.suspicious,
            "confidence": round(self.confidence, 4),
            "reasons": list(self.reasons),
        }


_INJECTION_PATTERNS = (
    r"ignore\s+(?:(?:all|any)\s+)?(?:previous|prior|earlier)\s+instructions",
    r"system\s+message",
    r"developer\s+message",
    r"reveal\s+(?:the|your)\s+(?:prompt|instructions|secrets?)",
    r"send\s+(?:this|the)\s+(?:data|information)\s+to",
    r"upload\s+(?:this|the)\s+(?:file|data)",
    r"disable\s+(?:security|safety|antivirus|approval)",
    r"bypass\s+(?:security|approval|authentication)",
)


def assess_file(path: str | Path, expected_hash: str | None = None, max_age_seconds: float | None = None) -> EvidenceAssessment:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    from .extractors import digest

    content_hash = digest(str(p))
    size = p.stat().st_size
    age = max(0.0, time.time() - p.stat().st_mtime)
    reasons: list[str] = []
    stale = max_age_seconds is not None and age > float(max_age_seconds)
    if stale:
        reasons.append("evidence_is_stale")
    if expected_hash and content_hash != expected_hash:
        reasons.append("content_hash_mismatch")
    confidence = 1.0
    if stale:
        confidence -= 0.35
    if expected_hash and content_hash != expected_hash:
        confidence = 0.0
    return EvidenceAssessment(
        ok=not reasons,
        content_hash=content_hash,
        size_bytes=size,
        age_seconds=age,
        stale=stale,
        suspicious=False,
        confidence=max(0.0, min(1.0, confidence)),
        reasons=reasons,
    )


def detect_prompt_injection(text: str) -> list[str]:
    """Detect common instruction-like attacks in untrusted media text.

    Detection is deliberately conservative: a hit produces a warning and
    confidence reduction, never an automatic refusal or action.
    """
    value = str(text or "")
    hits = []
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, value, re.I):
            hits.append(pattern)
    return hits


def assess_observation(observation, *, min_confidence: float = 0.35):
    """Attach deterministic reliability metadata to a MultimodalObservation."""
    text = "\n".join([observation.summary, observation.extracted_text, *observation.claims])
    hits = detect_prompt_injection(text)
    confidence = 1.0
    reasons = []
    if hits:
        confidence -= min(0.5, 0.15 * len(hits))
        observation.warnings.append("Potential prompt-injection-like content detected in evidence; treat it as untrusted data.")
        reasons.append("potential_prompt_injection")
    if observation.elements:
        scores = [max(0.0, min(1.0, float(e.confidence))) for e in observation.elements]
        confidence *= sum(scores) / len(scores)
    confidence = max(0.0, min(1.0, confidence))
    observation.warnings = list(dict.fromkeys(observation.warnings))
    # Metadata is intentionally additive so existing consumers remain compatible.
    setattr(observation, "reliability", {
        "confidence": round(confidence, 4),
        "suspicious": bool(hits),
        "reasons": reasons,
        "actionable": confidence >= float(min_confidence) and not hits,
    })
    return observation
