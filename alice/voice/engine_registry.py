"""Deterministic registry for ALICE-owned local voice engines."""
from __future__ import annotations
from dataclasses import dataclass

from .local_engine import LocalVoiceEngineGate


@dataclass(frozen=True)
class EngineAdmission:
    name: str
    admitted: bool
    reason: str


class LocalVoiceEngineRegistry:
    """Keep local engines discoverable without making cloud TTS a core dependency."""

    def __init__(self) -> None:
        self._engines: dict[str, object] = {}
        self._gate = LocalVoiceEngineGate()

    def register(self, engine: object) -> EngineAdmission:
        name = str(getattr(engine, "name", "") or "").strip()
        if not name:
            return EngineAdmission("", False, "engine_name_missing")
        readiness = self._gate.evaluate(engine)
        if not readiness.ready:
            return EngineAdmission(name, False, readiness.reason)
        self._engines[name] = engine
        return EngineAdmission(name, True, "engine_registered")

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._engines))

    def select(self, preferred: str | None = None) -> object | None:
        if preferred:
            engine = self._engines.get(str(preferred).strip())
            if engine is not None and self._gate.evaluate(engine).ready:
                return engine
        for name in self.available():
            engine = self._engines[name]
            if self._gate.evaluate(engine).ready:
                return engine
        return None
