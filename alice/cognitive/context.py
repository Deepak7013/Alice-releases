from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import re

@dataclass
class ExecutiveKnowledgeContext:
    request: str
    user_facts: list[Any] = field(default_factory=list)
    lessons: list[Any] = field(default_factory=list)
    world: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

class KnowledgeContextBuilder:
    """Builds bounded, provenance-aware context for reasoning; never executes actions."""
    VERSION='v3.50.0'
    def __init__(self, user_model=None, learning_store=None, world_model=None):
        self.user_model=user_model; self.learning_store=learning_store; self.world_model=world_model
    def _relevant(self, store, q, limit):
        if store is None:
            return []
        exact = list(store.search(q, verified_only=True))
        if exact:
            return exact[:limit]
        tokens = [t for t in re.findall(r"[a-zA-Z0-9_]{4,}", q.lower())
                  if t not in {"what", "with", "from", "that", "this", "using", "plan", "task"}]
        scored=[]; seen=set()
        for token in tokens:
            for item in store.search(token, verified_only=True):
                key=getattr(item, "key", "")
                if key in seen:
                    continue
                seen.add(key)
                hay=f"{getattr(item, 'key', '')} {getattr(item, 'value', '')}".lower()
                score=sum(1 for t in tokens if t in hay)
                scored.append((score, getattr(item, "updated_at", 0), item))
        scored.sort(key=lambda x:(-x[0], -x[1]))
        return [item for _,_,item in scored[:limit]]

    def build(self, request: str, *, query: str|None=None, world_context: bool=True, limit=8):
        q=str(query if query is not None else request)
        user=self._relevant(self.user_model, q, limit)
        lessons=self._relevant(self.learning_store, q, limit)
        world={}
        if self.world_model and world_context:
            # Planning receives freshness/provenance metadata only. Raw observations,
            # entity identifiers, and conflict values must not cross this bridge.
            try:
                summary_fn=getattr(self.world_model,"planning_summary",None)
                observed=summary_fn(q,max_chars=1200) if callable(summary_fn) else ""
                if observed:
                    world={'context':observed,'trust':'observation_only',
                           'policy':'metadata_only; values and identifiers omitted'}
            except Exception:
                # A broken or unavailable observer must not leak a raw-context fallback.
                world={}
        sources=[]
        if user: sources.append('user_model:verified')
        if lessons: sources.append('learning:verified')
        if world: sources.append('world_model:observations')
        return ExecutiveKnowledgeContext(str(request), user, lessons, world, sources)
