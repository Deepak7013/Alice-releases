from __future__ import annotations
"""Deterministic chat-memory promotion gate for ALICE v3.57.

The promotion gate separates *candidate memories* from durable memories.  User
messages may propose facts, preferences or instructions, but a candidate is not
silently authoritative merely because it came from chat.  Conflicts are surfaced
instead of overwriting existing durable knowledge, and credential/authority
material is rejected before persistence.
"""
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import json
import math
import os
import threading
from pathlib import Path
import time
from typing import Any

from .models import MemoryItem, MemoryKind, MemoryScope
from alice.knowledge.security import sanitize


_AUDIT_LOCKS: dict[str, threading.Lock] = {}
_AUDIT_LOCKS_GUARD = threading.Lock()


class PromotionStatus(str, Enum):
    ACCEPTED = "accepted"
    CONFLICT = "conflict"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


@dataclass
class MemoryCandidate:
    content: str
    kind: MemoryKind
    scope: MemoryScope = MemoryScope.USER
    confidence: float = 0.9
    source: str = "chat"
    tags: list[str] | None = None

    def __post_init__(self):
        if not isinstance(self.content, str):
            raise TypeError("candidate content must be a string")
        self.content = self.content.strip()
        if not isinstance(self.kind, MemoryKind):
            raise TypeError("candidate kind must be a MemoryKind")
        if not isinstance(self.scope, MemoryScope):
            raise TypeError("candidate scope must be a MemoryScope")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise TypeError("candidate confidence must be numeric")
        if not math.isfinite(float(self.confidence)) or not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("candidate confidence must be finite and between 0 and 1")
        if not isinstance(self.source, str) or not self.source.strip() or len(self.source) > 256:
            raise ValueError("candidate source must be a non-empty string of at most 256 characters")
        if self.tags is None:
            self.tags = []
        if not isinstance(self.tags, list) or len(self.tags) > 64:
            raise ValueError("candidate tags must be a list containing at most 64 strings")
        if any(not isinstance(tag, str) or not tag.strip() or len(tag) > 128 for tag in self.tags):
            raise ValueError("candidate tags must be non-empty strings of at most 128 characters")
        if len(self.content) > 10000:
            raise ValueError("candidate content exceeds the 10000 character limit")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass
class PromotionResult:
    status: PromotionStatus
    candidate: MemoryCandidate
    reason: str
    memory_hash: str | None = None
    conflicts: list[dict[str, Any]] | None = None


class MemoryPromotionEngine:
    """Gate candidate chat knowledge before it becomes durable context.

    This engine is advisory and has no authority to execute actions or grant
    permissions.  Explicit user-provided instructions can be stored as durable
    instructions, but they still cannot grant permissions because MemoryPolicy
    remains authoritative downstream.
    """

    def __init__(self, memory, audit_path: str | Path | None = None):
        self.memory = memory
        root = Path(audit_path) if audit_path else Path(getattr(memory, "path", "alice_context.db")).parent / "memory_promotion.jsonl"
        self.audit_path = root
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        # Promotion engines sharing a log must serialize within this process;
        # per-instance locks allow concurrent O_APPEND writes to race on
        # Windows and can otherwise drop or interleave audit records.
        lock_key = os.path.normcase(str(self.audit_path.resolve()))
        with _AUDIT_LOCKS_GUARD:
            self._audit_lock = _AUDIT_LOCKS.setdefault(lock_key, threading.Lock())

    @staticmethod
    def _is_authority_or_secret(text: str) -> bool:
        cleaned, redacted, authority = sanitize(text)
        lower = text.lower()
        explicit_secret = any(token in lower for token in ("api key:", "api_key=", "access token:", "password:", "secret:"))
        explicit_authority = any(token in lower for token in ("grant me permission", "bypass security", "disable security", "ignore security"))
        return bool(redacted or authority or cleaned != text or explicit_secret or explicit_authority)

    def _existing(self, candidate: MemoryCandidate) -> list[MemoryItem]:
        items = self.memory.list_active(candidate.scope)
        return [x for x in items if x.kind == candidate.kind]

    def evaluate(self, candidate: MemoryCandidate) -> PromotionResult:
        if not candidate.content or len(candidate.content) < 4:
            return PromotionResult(PromotionStatus.REJECTED, candidate, "empty_or_too_short")
        if self._is_authority_or_secret(candidate.content):
            return PromotionResult(PromotionStatus.REJECTED, candidate, "credential_or_authority_content")

        for item in self._existing(candidate):
            if item.content_hash == candidate.fingerprint:
                return PromotionResult(PromotionStatus.DUPLICATE, candidate, "already_present", item.content_hash, [])

        conflicts = []
        # Deterministic conflict heuristic: same durable kind/scope with
        # substantial token overlap but different normalized content.
        new_terms = set(candidate.content.lower().split())
        for item in self._existing(candidate):
            old_terms = set(item.content.lower().split())
            union = new_terms | old_terms
            overlap = len(new_terms & old_terms) / max(1, len(union))
            if overlap >= 0.45:
                conflicts.append({"hash": item.content_hash, "content": item.content, "confidence": item.confidence, "overlap": round(overlap, 3)})
        if conflicts:
            return PromotionResult(PromotionStatus.CONFLICT, candidate, "possible_existing_conflict", conflicts=conflicts)
        return PromotionResult(PromotionStatus.ACCEPTED, candidate, "safe_candidate")

    def promote(self, candidate: MemoryCandidate, *, confirmed: bool = False) -> PromotionResult:
        if not isinstance(confirmed, bool):
            raise TypeError("confirmed must be a boolean")
        result = self.evaluate(candidate)
        if result.status == PromotionStatus.CONFLICT and not confirmed:
            self._audit(result)
            return result
        if result.status not in {PromotionStatus.ACCEPTED, PromotionStatus.CONFLICT}:
            self._audit(result)
            return result
        item = MemoryItem(
            content=candidate.content,
            kind=candidate.kind,
            scope=candidate.scope,
            confidence=candidate.confidence,
            source=candidate.source,
            tags=candidate.tags,
        )
        memory_hash = self.memory.add(item)
        result.memory_hash = memory_hash
        # Confirmation authorizes adding a conflicting candidate; it does not
        # establish that the previous memory was deleted or superseded.
        result.reason = "confirmed_conflict_added_for_review" if result.status == PromotionStatus.CONFLICT else result.reason
        if result.status == PromotionStatus.CONFLICT:
            result.status = PromotionStatus.ACCEPTED
        self._audit(result)
        return result

    def _audit(self, result: PromotionResult) -> None:
        row = {
            "timestamp": time.time(),
            "status": result.status.value,
            "reason": result.reason,
            "kind": result.candidate.kind.value,
            "scope": result.candidate.scope.value,
            "candidate_hash": result.candidate.fingerprint,
            "memory_hash": result.memory_hash,
        }
        encoded = (json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
        # O_APPEND keeps each audit record at the end even if another engine
        # instance writes concurrently. A short write is treated as an error.
        with self._audit_lock:
            fd = os.open(self.audit_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                written = os.write(fd, encoded)
                if written != len(encoded):
                    raise OSError("incomplete memory promotion audit write")
                os.fsync(fd)
            finally:
                os.close(fd)
