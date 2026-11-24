from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import time, hashlib

class MemoryKind(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    GOAL = "goal"
    RELATIONSHIP = "relationship"
    EVENT = "event"
    PATTERN = "pattern"
    LESSON = "lesson"
    INSTRUCTION = "instruction"

class MemoryScope(str, Enum):
    SELF = "self"
    USER = "user"
    PROJECT = "project"
    SESSION = "session"
    GENERAL = "general"

@dataclass
class MemoryItem:
    content: str
    kind: MemoryKind
    scope: MemoryScope = MemoryScope.GENERAL
    confidence: float = 0.5
    source: str = "unknown"
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_confirmed_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    content_hash: str = field(init=False)

    def __post_init__(self):
        self.confidence = max(0.0, min(1.0, self.confidence))
        self.content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def is_active(self, now=None):
        now = now or time.time()
        return self.expires_at is None or now < self.expires_at
