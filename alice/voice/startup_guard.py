"""Deterministic voice startup selection and fallback guard."""
from __future__ import annotations
from dataclasses import dataclass
from .local_engine import LocalVoiceReadiness


@dataclass(frozen=True)
class VoiceStartupDecision:
    ready: bool
    primary: str | None
    fallback: str | None
    reason: str


class VoiceStartupGuard:
    def evaluate(self, local: LocalVoiceReadiness, sapi_ready: bool) -> VoiceStartupDecision:
        if local.ready:
            return VoiceStartupDecision(True, "local", "sapi" if sapi_ready else None, "local_ready")
        if sapi_ready:
            return VoiceStartupDecision(True, "sapi", "sapi", "local_unready_sapi_fallback")
        return VoiceStartupDecision(False, None, None, "no_verified_voice_path")
