"""Independent postcondition verification for runtime tool side effects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PostconditionResult:
    """A verifier result backed by separately observed state."""

    ok: bool
    evidence: dict[str, Any]
    reason: str = ""


class PostconditionRegistry:
    """Map mutating tools to independent, tool-specific state observers."""

    def __init__(self):
        self._verifiers: dict[str, Callable[[dict[str, Any], Any], PostconditionResult]] = {}

    def register(self, tool_name: str, verifier: Callable, *, replace: bool = False) -> None:
        name = str(tool_name).strip()
        if not name or not callable(verifier):
            raise ValueError("A tool name and callable postcondition verifier are required")
        if name in self._verifiers and not replace:
            raise ValueError(f"A postcondition verifier is already registered for {name}")
        self._verifiers[name] = verifier

    def has(self, tool_name: str) -> bool:
        return str(tool_name) in self._verifiers

    def verify(self, tool_name: str, args: dict[str, Any], result: Any) -> PostconditionResult:
        verifier = self._verifiers.get(str(tool_name))
        if verifier is None:
            return PostconditionResult(False, {"observed": False}, "no_postcondition_registered")
        try:
            outcome = verifier(dict(args or {}), result)
        except Exception as exc:
            return PostconditionResult(False, {"observed": False}, f"verifier_error:{type(exc).__name__}")
        if not isinstance(outcome, PostconditionResult):
            return PostconditionResult(False, {"observed": False}, "verifier_returned_unstructured_result")
        evidence = outcome.evidence if isinstance(outcome.evidence, dict) else {}
        if outcome.ok and evidence.get("observed") is not True:
            return PostconditionResult(False, {"observed": False}, "verified_result_requires_observed_evidence")
        return PostconditionResult(bool(outcome.ok), dict(evidence), str(outcome.reason or ""))
