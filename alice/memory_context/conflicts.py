from dataclasses import dataclass
from typing import List
from .models import MemoryItem

@dataclass
class MemoryConflict:
    existing: MemoryItem
    incoming: MemoryItem
    reason: str

class ConflictResolver:
    def find_conflicts(self, incoming: MemoryItem, existing: List[MemoryItem]):
        out = []
        incoming_words = set(incoming.content.lower().split())
        for item in existing:
            if item.kind == incoming.kind and item.scope == incoming.scope:
                words = set(item.content.lower().split())
                if len(incoming_words & words) >= 2 and incoming.content_hash != item.content_hash:
                    out.append(MemoryConflict(item, incoming, "same semantic category with overlapping terms"))
        return out
