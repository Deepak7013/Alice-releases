"""Governance policy for ALICE's locally owned voice engine.

This policy makes cloud TTS an architectural non-requirement. It is a decision
contract only: it does not install, select, or invoke any voice provider.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceOwnershipDecision:
    allowed: bool
    primary: str | None
    fallback: str | None
    reason: str


class LocalVoiceOwnershipPolicy:
    """Require a local primary voice path and preserve a local fallback."""

    def evaluate(self, *, local_ready: bool, fallback_ready: bool, requested_primary: str = "local") -> VoiceOwnershipDecision:
        primary = str(requested_primary or "").strip().lower()
        if primary not in {"local", ""}:
            return VoiceOwnershipDecision(False, None, None, "non_local_primary_forbidden")
        if local_ready:
            return VoiceOwnershipDecision(True, "local", "sapi" if fallback_ready else None, "local_primary_ready")
        if fallback_ready:
            return VoiceOwnershipDecision(True, "sapi", "sapi", "local_primary_unavailable_fallback_ready")
        return VoiceOwnershipDecision(False, None, None, "no_local_voice_path")
