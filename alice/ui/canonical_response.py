"""Canonical response lifecycle: one authoritative record for UI, memory and TTS."""
from dataclasses import dataclass
from time import time

@dataclass(frozen=True)
class CanonicalResponse:
    request_id: str
    text: str
    status: str
    speakable: bool
    recoverable: bool
    reason: str
    created_at: float

class CanonicalResponseStore:
    def __init__(self):
        self._records = {}

    def begin(self, request_id):
        self._records[str(request_id)] = {"parts": [], "status": "streaming", "reason": "", "recoverable": False}

    def append(self, request_id, piece):
        rec = self._records.setdefault(str(request_id), {"parts": [], "status": "streaming", "reason": "", "recoverable": False})
        text = str(piece or "")
        if text and rec["status"] == "streaming":
            rec["parts"].append(text)

    def finish(self, request_id, *, reason="completed"):
        rec = self._records.setdefault(str(request_id), {"parts": [], "status": "streaming", "reason": "", "recoverable": False})
        text = "".join(rec["parts"]).strip()
        rec.update(status="completed" if text else "failed", reason=reason, recoverable=False)
        return self._snapshot(request_id, speakable=bool(text))

    def fail(self, request_id, *, recoverable=True, reason="provider_failure"):
        rec = self._records.setdefault(str(request_id), {"parts": [], "status": "streaming", "reason": "", "recoverable": False})
        text = "".join(rec["parts"]).strip()
        rec.update(status="failed", reason=reason, recoverable=bool(recoverable and text))
        return self._snapshot(request_id, speakable=False)

    def _snapshot(self, request_id, *, speakable):
        rec = self._records[str(request_id)]
        return CanonicalResponse(str(request_id), "".join(rec["parts"]), rec["status"], bool(speakable), bool(rec["recoverable"]), rec["reason"], time())
