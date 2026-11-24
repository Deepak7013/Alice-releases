"""Contract and readiness gate for ALICE-owned local voice engines."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LocalVoiceReadiness:
    ready: bool
    engine: str | None
    offline: bool
    can_generate: bool
    reason: str


@runtime_checkable
class LocalVoiceEngine(Protocol):
    name: str
    offline: bool

    def can_generate(self, text: str) -> bool: ...
    def speak(self, text: str) -> bool: ...


class LocalVoiceEngineGate:
    """Admit only a genuinely local, offline-capable voice engine."""

    def evaluate(self, engine: object | None, text: str = "test") -> LocalVoiceReadiness:
        if engine is None:
            return LocalVoiceReadiness(False, None, False, False, "local_engine_missing")
        name = str(getattr(engine, "name", "") or "").strip()
        offline = bool(getattr(engine, "offline", False))
        if not name:
            return LocalVoiceReadiness(False, None, offline, False, "engine_name_missing")
        if not offline:
            return LocalVoiceReadiness(False, name, False, False, "offline_capability_required")
        checker = getattr(engine, "can_generate", None)
        if not callable(checker):
            return LocalVoiceReadiness(False, name, True, False, "generation_probe_missing")
        try:
            can_generate = bool(checker(str(text)))
        except Exception:
            can_generate = False
        if not can_generate:
            return LocalVoiceReadiness(False, name, True, False, "generation_probe_failed")
        return LocalVoiceReadiness(True, name, True, True, "local_engine_ready")
