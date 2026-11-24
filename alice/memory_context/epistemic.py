"""Epistemic layer for ALICE memory.

Separates what ALICE has heard from what she has verified. This layer is
advisory: it never grants permission or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid


class EpistemicStatus(str, Enum):
    ASSERTED = "asserted"
    INFERRED = "inferred"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"


@dataclass
class EpistemicRecord:
    record_id: str
    claim: str
    status: EpistemicStatus
    source: str
    confidence: float
    evidence: list[str]
    created_at: float
    updated_at: float
    supersedes: str | None = None


class EpistemicLedger:
    """Persistent claim ledger with strict recovery and atomic snapshots."""

    MAX_CLAIM = 10_000
    MAX_SOURCE = 200
    MAX_EVIDENCE_ITEMS = 100
    MAX_EVIDENCE_ITEM = 500
    MAX_RECORDS = 100_000

    def __init__(self, root=None):
        self.root = Path(root or Path.cwd()).resolve()
        self.path = self.root / "alice_workspace" / "epistemic_ledger.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: dict[str, EpistemicRecord] = {}
        self._lock = threading.RLock()
        self._load()

    @staticmethod
    def _validate_record(key, value):
        expected = {"record_id", "claim", "status", "source", "confidence",
                    "evidence", "created_at", "updated_at", "supersedes"}
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("epistemic ledger record has an invalid schema")
        rid = value["record_id"]
        if not isinstance(rid, str) or not rid or len(rid) > 64 or rid != key:
            raise ValueError("epistemic ledger record identifier is invalid")
        claim, source = value["claim"], value["source"]
        if not isinstance(claim, str) or not claim.strip() or len(claim) > EpistemicLedger.MAX_CLAIM:
            raise ValueError("epistemic ledger claim is invalid")
        if not isinstance(source, str) or not source.strip() or len(source) > EpistemicLedger.MAX_SOURCE:
            raise ValueError("epistemic ledger source is invalid")
        try:
            status = EpistemicStatus(value["status"])
        except (TypeError, ValueError) as exc:
            raise ValueError("epistemic ledger status is invalid") from exc
        confidence = value["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("epistemic ledger confidence is invalid")
        evidence = value["evidence"]
        if not isinstance(evidence, list) or len(evidence) > EpistemicLedger.MAX_EVIDENCE_ITEMS:
            raise ValueError("epistemic ledger evidence is invalid")
        if any(not isinstance(item, str) or len(item) > EpistemicLedger.MAX_EVIDENCE_ITEM for item in evidence):
            raise ValueError("epistemic ledger evidence item is invalid")
        for field in ("created_at", "updated_at"):
            stamp = value[field]
            if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp <= 0:
                raise ValueError(f"epistemic ledger {field} is invalid")
        supersedes = value["supersedes"]
        if supersedes is not None and (not isinstance(supersedes, str) or not supersedes or len(supersedes) > 64):
            raise ValueError("epistemic ledger supersedes reference is invalid")
        return EpistemicRecord(rid, claim, status, source, float(confidence), list(evidence),
                               float(value["created_at"]), float(value["updated_at"]), supersedes)

    def _load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or len(raw) > self.MAX_RECORDS:
                raise ValueError("epistemic ledger root is invalid")
            loaded = {key: self._validate_record(key, value) for key, value in raw.items()}
        except Exception as exc:
            # Never silently replace a corrupt ledger with an empty one: doing so
            # would erase provenance and make old claims appear never to exist.
            raise ValueError(f"Cannot safely load epistemic ledger at {self.path}: {exc}") from exc
        self.records = loaded

    def _snapshot(self, records=None):
        source = self.records if records is None else records
        return {key: asdict(record) | {"status": record.status.value}
                for key, record in source.items()}

    def _save(self, records=None):
        payload = json.dumps(self._snapshot(records), ensure_ascii=False, indent=2,
                             allow_nan=False).encode("utf-8")
        fd, temp_name = tempfile.mkstemp(prefix=".epistemic-ledger-", suffix=".tmp",
                                         dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
            try:
                dir_fd = os.open(str(self.path.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                # Some platforms/filesystems do not support directory fsync.
                pass
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    @staticmethod
    def _public(record):
        return asdict(record) | {"status": record.status.value}

    def add(self, claim, *, source="unknown", confidence=0.5,
            status=EpistemicStatus.ASSERTED, evidence=None, supersedes=None):
        if not isinstance(claim, str) or not claim.strip() or len(claim) > self.MAX_CLAIM:
            raise ValueError("claim must be a non-empty bounded string")
        if not isinstance(source, str) or not source.strip() or len(source) > self.MAX_SOURCE:
            raise ValueError("source must be a non-empty bounded string")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be a finite number from 0 to 1")
        try:
            status = EpistemicStatus(status)
        except (TypeError, ValueError) as exc:
            raise ValueError("status is invalid") from exc
        if evidence is None:
            evidence = []
        if not isinstance(evidence, (list, tuple)) or len(evidence) > self.MAX_EVIDENCE_ITEMS:
            raise ValueError("evidence must be a bounded list of strings")
        if any(not isinstance(item, str) or len(item) > self.MAX_EVIDENCE_ITEM for item in evidence):
            raise ValueError("evidence items must be bounded strings")
        if supersedes is not None and (not isinstance(supersedes, str) or not supersedes):
            raise ValueError("supersedes must be a record identifier")
        with self._lock:
            if len(self.records) >= self.MAX_RECORDS:
                raise ValueError("epistemic ledger record limit reached")
            if supersedes is not None and supersedes not in self.records:
                raise KeyError(supersedes)
            now = time.time()
            rec = EpistemicRecord(uuid.uuid4().hex[:16], claim.strip(), status,
                                  source[:self.MAX_SOURCE], float(confidence), list(evidence),
                                  now, now, supersedes)
            updated = dict(self.records)
            updated[rec.record_id] = rec
            if supersedes is not None:
                prior = updated[supersedes]
                updated[supersedes] = EpistemicRecord(
                    prior.record_id, prior.claim, EpistemicStatus.SUPERSEDED,
                    prior.source, prior.confidence, list(prior.evidence),
                    prior.created_at, now, prior.supersedes)
            self._save(updated)
            self.records = updated
            return self._public(rec)

    def _update(self, record_id, *, status, evidence, confidence):
        if not isinstance(record_id, str) or not record_id:
            raise KeyError(record_id)
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("evidence is required")
        with self._lock:
            rec = self.records.get(record_id)
            if rec is None:
                raise KeyError(record_id)
            if len(rec.evidence) >= self.MAX_EVIDENCE_ITEMS:
                raise ValueError("epistemic ledger evidence limit reached")
            updated = dict(self.records)
            changed = EpistemicRecord(rec.record_id, rec.claim, status, rec.source,
                                      confidence(rec.confidence), rec.evidence + [evidence[:self.MAX_EVIDENCE_ITEM]],
                                      rec.created_at, time.time(), rec.supersedes)
            updated[record_id] = changed
            self._save(updated)
            self.records = updated
            return self._public(changed)

    def verify(self, record_id, evidence):
        return self._update(record_id, status=EpistemicStatus.VERIFIED,
                            evidence=evidence, confidence=lambda old: max(old, 0.8))

    def dispute(self, record_id, reason):
        return self._update(record_id, status=EpistemicStatus.DISPUTED,
                            evidence=reason, confidence=lambda old: min(old, 0.4))

    def get(self, record_id):
        with self._lock:
            rec = self.records.get(str(record_id))
            return self._public(rec) if rec else None

    def current(self, claim_contains=None):
        if claim_contains is not None and not isinstance(claim_contains, str):
            raise ValueError("claim_contains must be a string")
        needle = (claim_contains or "").lower().strip()
        with self._lock:
            rows = [self._public(rec) for rec in self.records.values()
                    if rec.status != EpistemicStatus.SUPERSEDED
                    and (not needle or needle in rec.claim.lower())]
        return sorted(rows, key=lambda row: (row["confidence"], row["updated_at"]), reverse=True)
