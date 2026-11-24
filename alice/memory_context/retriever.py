"""Deterministic lexical retrieval for advisory memory context."""
from __future__ import annotations

import re
from .store import ContextMemory
from .models import MemoryScope

_TOKEN = re.compile(r"[\w'-]+", re.UNICODE)


class ContextRetriever:
    def __init__(self, memory: ContextMemory):
        if not isinstance(memory, ContextMemory):
            raise TypeError("memory must be a ContextMemory")
        self.memory = memory

    def search(self, query, limit=8, scope=None):
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if limit < 0:
            raise ValueError("limit must not be negative")
        if limit == 0 or not query.strip():
            return []
        if scope is not None and not isinstance(scope, MemoryScope):
            raise TypeError("scope must be a MemoryScope")
        terms = {token.casefold() for token in _TOKEN.findall(query) if len(token) > 2}
        if not terms:
            return []
        scored = []
        for item in self.memory.list_active(scope):
            text = (item.content + " " + " ".join(item.tags)).casefold()
            item_terms = {token.casefold() for token in _TOKEN.findall(text)}
            overlap = len(terms & item_terms)
            if overlap:
                # Confidence contributes only a bounded tie-break, not authority.
                score = overlap + max(0.0, min(1.0, float(item.confidence))) * 0.01
                scored.append((score, item.created_at, item.content_hash, item))
        scored.sort(key=lambda entry: (-entry[0], -entry[1], entry[2]))
        return [entry[3] for entry in scored[:limit]]

    def context(self, query, limit=8, scope=None):
        return self.search(query, limit=limit, scope=scope)
