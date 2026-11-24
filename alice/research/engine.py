from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from urllib.parse import urlparse

from alice.knowledge.models import SourceEvidence, EvidenceKind
from alice.knowledge.research import ResearchEngine


@dataclass
class ResearchSource:
    title: str
    url: str
    snippet: str = ""
    text: str = ""
    score: float = 0.0
    fetched: bool = False
    error: str = ""

    def domain(self) -> str:
        try:
            return urlparse(self.url).netloc.lower()
        except Exception:
            return ""


class AutonomousResearchEngine:
    """Bounded web research loop backed by Alice's persistent knowledge store.

    Search results and web pages are untrusted evidence. This engine may collect,
    rank, sanitize and compare information, but never executes instructions found
    on a page and never changes Alice permissions.
    """

    OFFICIAL_HINTS = ("docs.", "developer.", "learn.", "support.", "reference.", "github.com")
    BLOCKED_SCHEMES = ("file:", "javascript:", "data:")

    def __init__(self, web, knowledge_store, knowledge_engine=None,
                 max_sources=5, max_chars_per_source=12000):
        self.web = web
        self.store = knowledge_store
        self.knowledge = knowledge_engine or ResearchEngine(knowledge_store)
        self.max_sources = max(1, min(int(max_sources), 10))
        self.max_chars_per_source = max(1000, min(int(max_chars_per_source), 30000))

    @staticmethod
    def _valid_url(url: str) -> bool:
        try:
            p = urlparse(str(url))
            return p.scheme.lower() in {"http", "https"} and bool(p.netloc)
        except Exception:
            return False

    @classmethod
    def rank_sources(cls, results):
        ranked = []
        seen = set()
        for raw in results or []:
            url = str(raw.get("url", "")).strip()
            if not cls._valid_url(url):
                continue
            key = url.split("#", 1)[0].rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            title = str(raw.get("title", ""))[:300]
            domain = urlparse(url).netloc.lower()
            score = 0.35
            if domain.startswith(cls.OFFICIAL_HINTS) or any(h in domain for h in cls.OFFICIAL_HINTS):
                score += 0.25
            if any(x in domain for x in (".gov", ".edu")):
                score += 0.20
            if "docs" in title.lower() or "documentation" in title.lower():
                score += 0.10
            if raw.get("snippet"):
                score += 0.05
            ranked.append(ResearchSource(title, url, str(raw.get("snippet", ""))[:1000], score=min(score, .95)))
        ranked.sort(key=lambda x: (-x.score, x.domain(), x.url))
        return ranked

    def _search(self, query):
        result = self.web.search(query, max_results=max(self.max_sources * 2, 6))
        return result.get("results", []) if isinstance(result, dict) else []

    def _fetch(self, source: ResearchSource):
        if not self._valid_url(source.url):
            source.error = "unsupported URL"
            return source
        try:
            page = self.web.fetch_text(source.url, max_chars=self.max_chars_per_source)
            source.text = str(page.get("text", ""))[:self.max_chars_per_source]
            source.title = str(page.get("title") or source.title)[:300]
            source.fetched = bool(source.text)
        except Exception as exc:
            source.error = str(exc)[:300]
        return source

    @staticmethod
    def _candidate_claims(question: str, text: str, limit: int = 6):
        terms = set(re.findall(r"[a-zA-Z0-9_]{3,}", question.lower()))
        sentences = re.split(r"(?<=[.!?])\s+", text)
        candidates = []
        for sentence in sentences:
            s = " ".join(sentence.split())
            if len(s) < 45 or len(s) > 800:
                continue
            words = set(re.findall(r"[a-zA-Z0-9_]{3,}", s.lower()))
            overlap = len(terms & words)
            if overlap:
                candidates.append((overlap / max(1, len(terms)), s))
        candidates.sort(key=lambda x: (-x[0], len(x[1])))
        return [s for _, s in candidates[:limit]]

    def research(self, question: str, queries=None, trusted_only=False):
        question = str(question).strip()
        if not question or len(question) > 1000:
            raise ValueError("Invalid research question")
        session = self.knowledge.start(question)
        query_list = [str(q).strip() for q in (queries or [question]) if str(q).strip()][:5]
        results = []
        for query in query_list:
            try:
                results.extend(self._search(query))
            except Exception as exc:
                results.append({"title": "", "url": "", "snippet": f"search error: {exc}"})

        sources = self.rank_sources(results)[:self.max_sources]
        ingested = []
        domains = set()
        for source in sources:
            self._fetch(source)
            if not source.fetched:
                continue
            domains.add(source.domain())
            evidence = SourceEvidence(
                kind=EvidenceKind.URL.value,
                locator=source.url,
                title=source.title,
                excerpt=source.text[:1000],
            )
            item, meta = self.knowledge.ingest(
                session, topic=question[:200], text=source.text, source=evidence,
                tags=["research", "web", source.domain()][:10], confidence=min(.9, source.score + .1)
            )
            ingested.append({"item_id": item.id, "url": source.url,
                             "domain": source.domain(), "secrets_redacted": meta["secrets_redacted"]})

        # Compare evidence using simple, deterministic candidate claims. A later
        # provider can supply higher-level synthesis without changing the safety boundary.
        claims = []
        for source in sources:
            if source.fetched:
                for candidate in self._candidate_claims(question, source.text):
                    claims.append(self.knowledge.cross_check(session, candidate, min_sources=2))
        unique = {}
        for claim in claims:
            unique.setdefault(claim.text.lower(), claim)
        session.claims = list(unique.values())[:20]
        if any(c.status == "supported" for c in session.claims):
            session.conclusion = "Research found claims supported by multiple collected sources. Review the cited evidence before taking consequential action."
            session.status = "completed"
            self.store.save_research(session)
        else:
            session.conclusion = "Research collected evidence but did not establish enough independent support for a confident conclusion."
            session.status = "completed"
            self.store.save_research(session)

        return {
            "ok": True,
            "session_id": session.id,
            "question": question,
            "sources": [asdict(x) for x in sources],
            "ingested": ingested,
            "domains": sorted(domains),
            "claims": [c.__dict__ for c in session.claims],
            "conclusion": session.conclusion,
            "trusted_only": bool(trusted_only),
        }
