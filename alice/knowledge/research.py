
from __future__ import annotations
import uuid
from .models import ResearchSession, SourceEvidence, Claim, EvidenceKind
from .security import sanitize
from .store import KnowledgeStore


class ResearchEngine:
    """Turns collected sources into persistent, provenance-aware research.

    This class does not execute instructions found in sources. It only stores
    evidence and lets the caller explicitly mark conclusions as trusted.
    """

    def __init__(self, store: KnowledgeStore):
        self.store = store

    def start(self, question: str) -> ResearchSession:
        session = ResearchSession(id=uuid.uuid4().hex, question=question[:1000])
        self.store.save_research(session)
        return session

    def ingest(self, session: ResearchSession, topic: str, text: str,
               source: SourceEvidence, tags=(), confidence=0.5,
               mark_trusted: bool = False):
        cleaned, redacted, authority = sanitize(text)
        # Source content is never trusted merely because it contains a claim
        # about permissions or security.
        trusted = bool(mark_trusted) and not authority
        item = self.store.create(
            topic=topic, text=cleaned, source=source.with_hash(cleaned),
            tags=tags, confidence=confidence, trusted=trusted
        )
        if item.id not in session.source_ids:
            session.source_ids.append(item.id)
        self.store.save_research(session)
        return item, {"secrets_redacted": redacted, "authority_text_detected": authority}

    def add_claim(self, session: ResearchSession, text: str,
                  evidence_ids=None, confidence=0.5, status="unverified", notes=""):
        claim = Claim(
            text=text[:3000], confidence=max(0, min(1, float(confidence))),
            evidence_ids=list(evidence_ids or []), status=status, notes=str(notes)[:1000]
        )
        session.claims.append(claim)
        self.store.save_research(session)
        return claim

    def cross_check(self, session: ResearchSession, claim_text: str,
                    min_sources: int = 2):
        normalized = set(claim_text.lower().split())
        sources = []
        for sid in session.source_ids:
            item = self.store.get(sid)
            if item:
                words = set(item.text.lower().split())
                overlap = len(normalized & words) / max(1, len(normalized))
                if overlap >= 0.20:
                    sources.append(item)
        if len(sources) >= min_sources:
            status = "supported"
            confidence = min(0.95, 0.55 + 0.12 * len(sources))
        elif sources:
            status = "unverified"
            confidence = min(0.65, 0.40 + 0.08 * len(sources))
        else:
            status = "disputed"
            confidence = 0.25
        claim = self.add_claim(
            session, claim_text, [x.id for x in sources],
            confidence=confidence, status=status
        )
        return claim

    def conclude(self, session: ResearchSession, conclusion: str,
                 require_supported_claims: bool = False):
        if require_supported_claims and any(c.status not in {"supported"} for c in session.claims):
            raise ValueError("Research contains claims that are not cross-checked")
        session.conclusion = conclusion[:6000]
        session.status = "completed"
        self.store.save_research(session)
        return session
