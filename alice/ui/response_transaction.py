"""Canonical response transaction for streamed ALICE replies.

Keeps the text already delivered to the UI authoritative when a provider
finishes empty or fails after partial output. Recovery is explicit and bounded.
"""
from dataclasses import dataclass
from .canonical_response import CanonicalResponseStore

@dataclass(frozen=True)
class ResponseState:
    text: str
    completed: bool
    recoverable: bool
    reason: str

class ResponseTransaction:
    def __init__(self):
        self._parts=[]
        self._finished=False
        self._failed=False
        self._canonical=CanonicalResponseStore()
        self._request_id=f"tx-{id(self)}"
        self._canonical.begin(self._request_id)

    def append(self, piece):
        if self._finished:
            return
        text=str(piece or "")
        if text:
            self._parts.append(text)
            self._canonical.append(self._request_id, text)

    @property
    def text(self):
        return "".join(self._parts)

    def complete(self):
        self._finished=True
        self._canonical.finish(self._request_id)
        return ResponseState(self.text, bool(self.text.strip()), False, "completed")

    def fail(self, recoverable=True):
        self._failed=True
        self._canonical.fail(self._request_id, recoverable=recoverable, reason="partial_failure" if self.text.strip() else "empty_failure")
        return ResponseState(self.text, False, bool(recoverable and self.text.strip()), "partial_failure" if self.text.strip() else "empty_failure")

    def empty(self):
        return not bool(self.text.strip())
