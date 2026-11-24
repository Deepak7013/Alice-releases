"""Bridge verified experience outcomes into the inert improvement proposal ledger.

This module is deliberately side-effect limited: it can record proposals and
rank them, but it cannot approve, edit source, execute code, or grant authority.
"""
from __future__ import annotations

from collections.abc import Iterable
from .proposals import ImprovementProposalLedger


class ExperienceProposalBridge:
    """Turn verified failures/lessons into structured engineering candidates."""

    def __init__(self, ledger: ImprovementProposalLedger):
        self.ledger = ledger

    def observe_failure(
        self,
        *,
        request: str,
        tools: Iterable[str] = (),
        summary: str = "",
        lessons: Iterable[str] = (),
        area: str = "execution",
        expected_benefit: str = "Improve reliability of the observed workflow",
    ):
        lessons = [str(x).strip() for x in lessons if str(x).strip()]
        evidence = {
            "kind": "verified_failure",
            "request": str(request)[:500],
            "tools": list(dict.fromkeys(str(x) for x in tools))[:30],
            "summary": str(summary)[:700],
            "lessons": lessons[:20],
        }
        problem = str(summary).strip() or (lessons[0] if lessons else f"Verified failure in: {request}")
        return self.ledger.propose(
            area=area,
            problem=problem,
            evidence=evidence,
            expected_benefit=expected_benefit,
        )

    def rank(self, limit: int = 10):
        """Return inert proposals ordered by conservative engineering priority."""
        rows = []
        for item in self.ledger.list():
            status_weight = {
                "proposed": 2,
                "engineering_review": 1,
                "completed": 0,
                "rejected": 0,
            }.get(item.get("status"), 0)
            evidence = item.get("evidence", "")
            evidence_weight = 1 if evidence else 0
            rows.append((status_weight + evidence_weight, item.get("created_at", 0), item))
        rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [x[2] for x in rows[: max(0, int(limit))]]
