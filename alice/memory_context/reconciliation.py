"""Deterministic reconciliation for ALICE epistemic claims.

This layer decides how claims relate to one another; it never grants authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import re

from .epistemic import EpistemicLedger, EpistemicStatus

@dataclass(frozen=True)
class Reconciliation:
    status: str
    reason: str
    related_ids: tuple[str, ...] = ()

class EpistemicReconciler:
    """Find duplicates, likely contradictions, and stale claims deterministically."""
    NEGATIONS = re.compile(r"\b(not|never|no longer|isn't|isnt|cannot|can't|cant|disabled|unavailable|false)\b", re.I)

    def __init__(self, ledger: EpistemicLedger):
        self.ledger = ledger

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {x for x in re.findall(r"[a-z0-9_]+", text.lower()) if len(x) > 2}

    def compare(self, claim: str, *, kind: str = "fact", source: str = "unknown") -> list[Reconciliation]:
        claim = str(claim).strip()
        if not claim:
            return []
        incoming = self._tokens(claim)
        incoming_neg = bool(self.NEGATIONS.search(claim))
        out: list[Reconciliation] = []
        for row in self.ledger.current():
            existing = self._tokens(row["claim"])
            if not existing:
                continue
            overlap = len(incoming & existing) / max(1, len(incoming | existing))
            if overlap >= 0.85:
                out.append(Reconciliation("duplicate", "high lexical overlap", (row["record_id"],)))
            elif overlap >= 0.55 and incoming_neg != bool(self.NEGATIONS.search(row["claim"])):
                out.append(Reconciliation("potential_conflict", "shared subject with opposite polarity", (row["record_id"],)))
        return out

    def current_trust(self, record_id: str) -> float:
        row = self.ledger.get(record_id)
        if not row:
            return 0.0
        base = float(row.get("confidence", 0.0))
        status = row.get("status")
        if status == EpistemicStatus.VERIFIED.value:
            return min(1.0, base + 0.15)
        if status == EpistemicStatus.DISPUTED.value:
            return min(base, 0.25)
        if status == EpistemicStatus.SUPERSEDED.value:
            return 0.0
        return base
