"""Deterministic speech director for ALICE's local-owned voice pipeline."""
from __future__ import annotations
from dataclasses import dataclass

from .natural_pauses import plan_natural_pauses
from .prosody import ProsodyPlan, ProsodyPlanner
from .text_prep import apply_pronunciation


@dataclass(frozen=True)
class SpeechDirective:
    text: str
    segments: tuple[dict[str, object], ...]
    prosody: ProsodyPlan
    engine: str | None
    valid: bool
    reason: str


class SpeechDirector:
    """Prepare a complete, side-effect-free speech directive.

    The director only plans speech. It does not select cloud providers, synthesize
    audio, play audio, grant permissions, or mutate the active voice backend.
    """

    def __init__(self, prosody: ProsodyPlanner | None = None) -> None:
        self._prosody = prosody or ProsodyPlanner()

    def prepare(
        self,
        text: object,
        *,
        engine: object | None,
        profile: str = "natural",
        urgency: float = 0.0,
        pronunciation: dict[str, str] | None = None,
    ) -> SpeechDirective:
        prepared = apply_pronunciation(text, pronunciation)
        plan = self._prosody.plan(profile, urgency=urgency)
        if not prepared:
            return SpeechDirective("", (), plan, None, False, "speech_text_missing")
        if not plan.valid:
            return SpeechDirective(prepared, (), plan, None, False, "prosody_invalid")
        if engine is None:
            return SpeechDirective(prepared, (), plan, None, False, "engine_missing")
        name = str(getattr(engine, "name", "") or "").strip()
        local_owned = bool(getattr(engine, "local_owned", False))
        offline = bool(getattr(engine, "offline", False))
        remote_dependency = bool(getattr(engine, "remote_dependency", not local_owned))
        if not name:
            return SpeechDirective(prepared, (), plan, None, False, "engine_name_missing")
        if not local_owned or remote_dependency or not offline:
            return SpeechDirective(prepared, (), plan, name, False, "local_engine_required")
        segments = tuple(plan_natural_pauses(prepared))
        if not segments:
            return SpeechDirective(prepared, (), plan, name, False, "segments_missing")
        return SpeechDirective(prepared, segments, plan, name, True, "speech_directive_ready")
