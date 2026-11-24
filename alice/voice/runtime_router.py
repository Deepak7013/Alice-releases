"""Runtime routing for local neural speech with a local fallback."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from .text_prep import prepare_for_speech

from .engine_registry import LocalVoiceEngineRegistry


@dataclass(frozen=True)
class VoiceRuntimeResult:
    spoken: bool
    provider: str | None
    local_attempted: bool
    fallback_attempted: bool
    reason: str


class LocalVoiceRuntimeRouter:
    """Prefer an admitted offline engine, then use an injected local fallback.

    The fallback is expected to be the existing local Windows/SAPI voice adapter.
    This router never selects or invokes a cloud TTS provider.
    """
    def __init__(self, registry: LocalVoiceEngineRegistry, *, fallback: Callable[[str], object] | None = None,
                 max_text_chars: int = 20000) -> None:
        if not 1 <= int(max_text_chars) <= 100000:
            raise ValueError("max_text_chars_out_of_range")
        self.registry = registry
        self.fallback = fallback
        self.max_text_chars = int(max_text_chars)

    def speak(self, text: object) -> VoiceRuntimeResult:
        clean = prepare_for_speech(text)
        if not clean:
            return VoiceRuntimeResult(False, None, False, False, "text_missing_after_preparation")
        if len(clean) > self.max_text_chars:
            return VoiceRuntimeResult(False, None, False, False, "text_too_large")

        engine = self.registry.select()
        local_attempted = False
        if engine is not None:
            local_attempted = True
            try:
                if bool(engine.speak(clean)):
                    return VoiceRuntimeResult(True, str(getattr(engine, "name", "local")), True, False,
                                              "local_speech_played")
            except Exception:
                pass

        if self.fallback is None:
            return VoiceRuntimeResult(False, str(getattr(engine, "name", "local")) if engine else None,
                                      local_attempted, False, "local_voice_failed_no_fallback")
        try:
            ok = self.fallback(clean)
            if hasattr(ok, "spoken"):
                ok = getattr(ok, "spoken")
            if bool(ok):
                return VoiceRuntimeResult(True, "sapi_fallback", local_attempted, True,
                                          "local_fallback_played")
            return VoiceRuntimeResult(False, "sapi_fallback", local_attempted, True,
                                      "local_fallback_failed")
        except Exception:
            return VoiceRuntimeResult(False, "sapi_fallback", local_attempted, True,
                                      "local_fallback_exception")
