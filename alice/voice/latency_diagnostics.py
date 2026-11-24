"""Privacy-safe timing primitives for diagnosing ALICE speech latency.

The helper records durations only; it never records response text, credentials,
file paths, or audio. It does not alter playback behavior.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from time import perf_counter
from typing import Dict, Optional

@dataclass
class SpeechLatencyTrace:
    _started: float = field(default_factory=perf_counter, repr=False)
    _marks: Dict[str, float] = field(default_factory=dict, repr=False)

    def mark(self, stage: str, at: Optional[float] = None) -> float:
        if not isinstance(stage, str) or not stage.strip():
            raise ValueError("stage must be a non-empty string")
        now = perf_counter() if at is None else float(at)
        if now < self._started:
            raise ValueError("stage timestamp precedes trace start")
        self._marks[stage.strip()] = now
        return round((now - self._started) * 1000, 3)

    def report(self) -> dict:
        ordered = sorted(self._marks.items(), key=lambda item: item[1])
        previous = self._started
        stages = []
        for name, stamp in ordered:
            stages.append({"stage": name, "elapsed_ms": round((stamp-self._started)*1000, 3),
                           "since_previous_ms": round((stamp-previous)*1000, 3)})
            previous = stamp
        return {"schema": 1, "total_ms": round(((ordered[-1][1] if ordered else self._started)-self._started)*1000, 3),
                "stages": stages}
