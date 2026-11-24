"""Deterministic planning contract for ALICE-owned local speech generation."""
from __future__ import annotations
from dataclasses import dataclass


STAGES = (
    "normalize",
    "pronunciation",
    "context",
    "prosody",
    "segment",
    "synthesize",
    "playback",
)


@dataclass(frozen=True)
class SpeechPipelinePlan:
    stages: tuple[str, ...]
    local_required: bool
    engine: str | None
    text: str
    valid: bool
    reason: str


class LocalSpeechPipelinePlanner:
    """Create a side-effect-free plan for the local speech pipeline.

    Planning does not synthesize audio, select a cloud provider, grant permission,
    or start playback. It establishes the invariant that the local pipeline owns the
    speech path before later execution layers are allowed to act.
    """

    def plan(self, text: object, *, engine: object | None, local_required: bool = True) -> SpeechPipelinePlan:
        clean = str(text if text is not None else "").strip()
        if not clean:
            return SpeechPipelinePlan(STAGES, local_required, None, "", False, "text_missing")
        if engine is None:
            return SpeechPipelinePlan(STAGES, local_required, None, clean, False, "engine_missing")
        name = str(getattr(engine, "name", "") or "").strip()
        if not name:
            return SpeechPipelinePlan(STAGES, local_required, None, clean, False, "engine_name_missing")
        local_owned = bool(getattr(engine, "local_owned", False))
        remote_dependency = bool(getattr(engine, "remote_dependency", not local_owned))
        offline = bool(getattr(engine, "offline", False))
        if local_required and (not local_owned or remote_dependency or not offline):
            return SpeechPipelinePlan(STAGES, local_required, name, clean, False, "local_pipeline_required")
        return SpeechPipelinePlan(STAGES, local_required, name, clean, True, "local_pipeline_ready")
