
from __future__ import annotations
import math
import re
from .models import KnowledgeItem
from .store import KnowledgeStore


class KnowledgeRetriever:
    """Deterministic retrieval now; embedding/vector retrieval can be added later."""

    STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "what", "how"}

    def __init__(self, store: KnowledgeStore):
        self.store = store

    def retrieve(self, query: str, limit: int = 8, trusted_only: bool = False) -> list[KnowledgeItem]:
        candidates = self.store.search(query, limit=max(limit * 5, 20), trusted_only=trusted_only)
        q = set(self._tokens(query))
        scored = []
        for item in candidates:
            words = set(self._tokens(item.topic + " " + item.text + " " + " ".join(item.tags)))
            overlap = len(q & words)
            phrase_bonus = 1.0 if query.lower() in item.text.lower() else 0.0
            score = overlap / math.sqrt(max(1, len(q))) + phrase_bonus + item.confidence * 0.15
            scored.append((score, item))
        scored.sort(key=lambda x: (x[0], x[1].confidence, x[1].updated_at), reverse=True)
        return [x[1] for x in scored[:max(1, limit)]]

    def context(self, query: str, limit: int = 5, trusted_only: bool = False) -> str:
        items = self.retrieve(query, limit, trusted_only)
        return "\n\n".join(
            f"[{i+1}] topic={x.topic}; confidence={x.confidence:.2f}; "
            f"source={x.source.title or x.source.locator}\n{x.text[:3000]}"
            for i, x in enumerate(items)
        )

    @classmethod
    def _tokens(cls, text: str):
        return [x for x in re.findall(r"[a-zA-Z0-9_]{2,}", text.lower()) if x not in cls.STOP]
