"""Phase 10 observe/verify/recover primitives."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

@dataclass
class Observation:
    key: str
    value: Any
    expected: Any = None
    matches: Optional[bool] = None
    source: str = "runtime"

@dataclass
class RecoveryResult:
    verified: bool
    recovered: bool = False
    attempts: int = 0
    observations: list[Observation] = field(default_factory=list)
    message: str = ""

class ObserveVerifyRecover:
    """Bounded post-action verification and recovery; never grants permission."""
    VERSION = "v3.42.0"
    def __init__(self, max_retries: int = 2):
        self.max_retries = max(0, int(max_retries))
    def run(self, observe: Callable[[], Observation], recover: Optional[Callable[[], object]] = None) -> RecoveryResult:
        obs = observe()
        if obs.matches is True:
            return RecoveryResult(True, False, 0, [obs], "verified")
        if recover is None:
            return RecoveryResult(False, False, 0, [obs], "verification failed; no recovery available")
        observations=[obs]
        for attempt in range(1, self.max_retries+1):
            recover()
            obs=observe(); observations.append(obs)
            if obs.matches is True:
                return RecoveryResult(True, True, attempt, observations, "recovered and verified")
        return RecoveryResult(False, True, self.max_retries, observations, "recovery exhausted; verification failed")
