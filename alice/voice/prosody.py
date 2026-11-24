"""Deterministic prosody planning for ALICE local speech."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ProsodyPlan:
    rate: float
    pause_ms: int
    emphasis: str
    emotion: str
    valid: bool
    reason: str


class ProsodyPlanner:
    """Plan delivery characteristics without generating or playing audio."""
    PROFILES = {
        "natural": (1.0, 180, "moderate", "neutral"),
        "professional": (0.96, 220, "moderate", "calm"),
        "casual": (1.04, 140, "light", "warm"),
        "emergency": (1.12, 90, "strong", "urgent"),
        "storytelling": (0.92, 300, "expressive", "engaged"),
    }

    def plan(self, profile: str = "natural", *, urgency: float = 0.0) -> ProsodyPlan:
        key = str(profile or "").strip().lower()
        if key not in self.PROFILES:
            return ProsodyPlan(1.0, 180, "moderate", "neutral", False, "unknown_profile")
        rate, pause, emphasis, emotion = self.PROFILES[key]
        u = max(0.0, min(1.0, float(urgency)))
        rate = min(1.25, rate + 0.10 * u)
        pause = max(70, int(round(pause * (1.0 - 0.45 * u))))
        if u >= 0.75:
            emphasis = "strong"
            emotion = "urgent"
        return ProsodyPlan(rate, pause, emphasis, emotion, True, "prosody_ready")
