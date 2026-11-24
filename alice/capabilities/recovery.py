"""Bounded capability-gap recovery for failed tasks."""
from __future__ import annotations
import re

class CapabilityRecovery:
    """Identify genuine capability gaps and acquire only bounded, testable skills."""
    GAP_PATTERNS=(
        r"unknown tool", r"unavailable tool", r"missing capability", r"capability.*missing",
        r"not available", r"no.*capability", r"cannot.*perform.*because", r"unsupported.*operation",
    )
    TRANSIENT_PATTERNS=(r"sys\.stdin", r"sys\.stdout", r"timeout", r"connection", r"rate limit", r"402")
    def __init__(self, acquirer=None): self.acquirer=acquirer
    def classify(self, error):
        # Runtime errors use machine identifiers (``unknown_tool``), while
        # provider exceptions usually use prose. Normalize separators so both
        # forms follow the same bounded recovery policy.
        text=re.sub(r"[_-]+", " ", str(error or "").lower())
        if any(re.search(p,text) for p in self.TRANSIENT_PATTERNS): return "transient_or_provider"
        if any(re.search(p,text) for p in self.GAP_PATTERNS): return "capability_gap"
        return "unknown"
    def recover(self, goal, error, capability=""):
        if not self.acquirer or self.classify(error)!="capability_gap":
            return {"attempted":False,"reason":self.classify(error)}
        try:
            # In the app, the registered acquire_capability tool also stages
            # and activates the validated skill in ToolRegistry. Prefer it
            # over a raw acquirer so recovery makes newly built tools usable.
            acquire = getattr(self.acquirer, "acquire", None)
            if not callable(acquire) and callable(self.acquirer):
                acquire = self.acquirer
            if not callable(acquire):
                return {"attempted":False,"reason":"acquirer_unavailable"}
            result=acquire(goal, capability=capability, allow_research=True)
            return {"attempted":True,"result":result}
        except Exception as exc:
            return {"attempted":True,"error":str(exc)[:1000]}
