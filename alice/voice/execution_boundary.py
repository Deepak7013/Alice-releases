"""Governed execution boundary for ALICE-owned local voice engines."""
from __future__ import annotations
from dataclasses import dataclass

from .local_engine import LocalVoiceEngineGate


@dataclass(frozen=True)
class VoiceExecutionResult:
    attempted: bool
    succeeded: bool
    engine: str | None
    reason: str


class LocalVoiceExecutionBoundary:
    """Allow speech execution only after the existing local readiness gate passes."""

    def __init__(self) -> None:
        self._gate = LocalVoiceEngineGate()

    def execute(self, engine: object | None, text: object) -> VoiceExecutionResult:
        name = str(getattr(engine, "name", "") or "").strip() if engine is not None else None
        clean = str(text if text is not None else "").strip()
        if not clean:
            return VoiceExecutionResult(False, False, name, "text_missing")
        readiness = self._gate.evaluate(engine, clean)
        if not readiness.ready:
            return VoiceExecutionResult(False, False, name, readiness.reason)
        speak = getattr(engine, "speak", None)
        if not callable(speak):
            return VoiceExecutionResult(False, False, name, "speak_method_missing")
        try:
            ok = bool(speak(clean))
        except Exception:
            return VoiceExecutionResult(True, False, name, "engine_execution_failed")
        return VoiceExecutionResult(True, ok, name, "speech_played" if ok else "engine_reported_failure")
