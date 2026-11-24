"""Governed orchestration of ALICE's local speech preparation and execution."""
from __future__ import annotations
from dataclasses import dataclass

from .execution_boundary import LocalVoiceExecutionBoundary, VoiceExecutionResult
from .speech_director import SpeechDirector, SpeechDirective
from .cancellation import SpeechCancellation

@dataclass(frozen=True)
class SpeechRunResult:
    prepared: bool
    executed_segments: int
    failed_segments: int
    engine: str | None
    reason: str
    directive: SpeechDirective
    results: tuple[VoiceExecutionResult, ...]
    next_segment_index: int

class LocalSpeechOrchestrator:
    """Run local speech with a resume point and scoped cancellation callback."""
    def __init__(self, director: SpeechDirector | None = None,
                 boundary: LocalVoiceExecutionBoundary | None = None) -> None:
        self._director = director or SpeechDirector()
        self._boundary = boundary or LocalVoiceExecutionBoundary()

    def run(self, text: object, *, engine: object | None,
            profile: str = "natural", urgency: float = 0.0,
            pronunciation: dict[str, str] | None = None,
            start_segment: int = 0, cancellation: SpeechCancellation | None = None) -> SpeechRunResult:
        directive = self._director.prepare(text, engine=engine, profile=profile, urgency=urgency, pronunciation=pronunciation)
        if not directive.valid:
            return SpeechRunResult(False, 0, 0, directive.engine, directive.reason, directive, (), 0)
        if isinstance(start_segment, bool) or not isinstance(start_segment, int):
            return SpeechRunResult(False, 0, 0, directive.engine, "invalid_resume_index", directive, (), 0)
        if start_segment < 0 or start_segment > len(directive.segments):
            return SpeechRunResult(False, 0, 0, directive.engine, "resume_index_out_of_range", directive, (), 0)

        results: list[VoiceExecutionResult] = []
        stop = getattr(engine, "stop", None) if engine is not None else None
        registered = cancellation is not None and callable(stop)
        if registered:
            cancellation.register_stop(stop)
        try:
            for index in range(start_segment, len(directive.segments)):
                if cancellation is not None and cancellation.cancelled:
                    return SpeechRunResult(True, sum(r.succeeded for r in results), sum(not r.succeeded for r in results),
                                           directive.engine, "speech_cancelled", directive, tuple(results), index)
                result = self._boundary.execute(engine, directive.segments[index]["text"])
                results.append(result)
                if cancellation is not None and cancellation.cancelled:
                    # A segment reported successful before cancellation was observed;
                    # resume at the next segment to avoid replaying completed speech.
                    next_index = index + 1 if result.succeeded else index
                    return SpeechRunResult(True, sum(r.succeeded for r in results), sum(not r.succeeded for r in results),
                                           directive.engine, "speech_cancelled", directive, tuple(results), next_index)
                if not result.succeeded:
                    return SpeechRunResult(True, sum(r.succeeded for r in results), sum(not r.succeeded for r in results),
                                           directive.engine, "segment_execution_failed", directive, tuple(results), index)
            return SpeechRunResult(True, sum(r.succeeded for r in results), 0, directive.engine,
                                   "speech_run_complete", directive, tuple(results), len(directive.segments))
        finally:
            if registered and cancellation is not None:
                cancellation.unregister_stop(stop)
