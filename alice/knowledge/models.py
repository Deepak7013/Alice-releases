
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import hashlib
import time


class EvidenceKind(str, Enum):
    DOCUMENT = "document"
    URL = "url"
    TOOL_RESULT = "tool_result"
    WORKER_REPORT = "worker_report"
    CAPABILITY_RESEARCH = "capability_research"
    USER_PROVIDED = "user_provided"


@dataclass
class SourceEvidence:
    kind: str
    locator: str = ""
    title: str = ""
    excerpt: str = ""
    retrieved_at: float = field(default_factory=time.time)
    published_at: str | None = None
    content_hash: str = ""

    def with_hash(self, content: str) -> "SourceEvidence":
        self.content_hash = hashlib.sha256(content.encode("utf-8", "ignore")).hexdigest()
        return self


@dataclass
class Claim:
    text: str
    confidence: float = 0.5
    evidence_ids: list[str] = field(default_factory=list)
    status: str = "unverified"  # unverified, supported, disputed, rejected
    notes: str = ""


@dataclass
class KnowledgeItem:
    id: str
    topic: str
    text: str
    source: SourceEvidence
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    trusted: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(
                self.text.encode("utf-8", "ignore")
            ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source"] = asdict(self.source)
        return d


@dataclass
class ResearchSession:
    id: str
    question: str
    status: str = "open"
    source_ids: list[str] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    conclusion: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
