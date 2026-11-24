"""Tamper-evident chaining for verified ALICE local-model admission receipts."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from collections.abc import Sequence
from .model_admission_bridge import verify_model_admission_receipt

_ZERO = "0" * 64
MAX_RECEIPT_CHAIN_ENTRIES = 1024

@dataclass(frozen=True)
class ReceiptChainEntry:
    index: int
    previous_digest: str
    receipt_digest: str
    chain_digest: str


def _chain_digest(index: int, previous_digest: str, receipt_digest: str) -> str:
    payload = json.dumps({"index": index, "previous_digest": previous_digest, "receipt_digest": receipt_digest}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_verified_receipt(entries: Sequence[ReceiptChainEntry], receipt_json: object, receipt_digest: object) -> tuple[tuple[ReceiptChainEntry, ...], str]:
    """Append only a valid receipt; return the unchanged chain on rejection."""
    current = tuple(entries)
    if len(current) >= MAX_RECEIPT_CHAIN_ENTRIES:
        return current, "receipt_chain_full"
    valid, reason = verify_model_admission_receipt(receipt_json, receipt_digest)
    if not valid:
        return current, "receipt_rejected:" + reason
    ok, chain_reason = verify_receipt_chain(current)
    if not ok:
        return current, "existing_chain_invalid:" + chain_reason
    previous = current[-1].chain_digest if current else _ZERO
    index = len(current)
    entry = ReceiptChainEntry(index, previous, str(receipt_digest), _chain_digest(index, previous, str(receipt_digest)))
    return current + (entry,), "receipt_appended"


def verify_receipt_chain(entries: Sequence[ReceiptChainEntry]) -> tuple[bool, str]:
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, bytearray)):
        return False, "chain_invalid_type"
    if len(entries) > MAX_RECEIPT_CHAIN_ENTRIES:
        return False, "receipt_chain_too_large"
    previous = _ZERO
    for index, entry in enumerate(entries):
        if not isinstance(entry, ReceiptChainEntry):
            return False, "chain_entry_invalid"
        if entry.index != index or entry.previous_digest != previous:
            return False, "chain_sequence_mismatch"
        for value in (entry.receipt_digest, entry.chain_digest):
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                return False, "chain_digest_invalid"
        expected = _chain_digest(index, previous, entry.receipt_digest)
        if expected != entry.chain_digest:
            return False, "chain_digest_mismatch"
        previous = entry.chain_digest
    return True, "receipt_chain_verified"


def export_receipt_chain(entries: Sequence[ReceiptChainEntry]) -> str:
    """Serialize a valid bounded chain into canonical JSON for archival."""
    ok, reason = verify_receipt_chain(entries)
    if not ok:
        raise ValueError(reason)
    payload = {"format": 1, "entries": [
        {"index": e.index, "previous_digest": e.previous_digest, "receipt_digest": e.receipt_digest, "chain_digest": e.chain_digest}
        for e in entries
    ]}
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(text.encode("utf-8")) > 262144:
        raise ValueError("receipt_chain_export_too_large")
    return text


def import_receipt_chain(serialized: object) -> tuple[tuple[ReceiptChainEntry, ...], str]:
    """Validate bounded chain JSON before exposing immutable entries."""
    if not isinstance(serialized, str):
        return (), "receipt_chain_serialization_invalid"
    if len(serialized.encode("utf-8")) > 262144:
        return (), "receipt_chain_serialization_too_large"
    try:
        payload = json.loads(serialized)
    except Exception:
        return (), "receipt_chain_json_invalid"
    if not isinstance(payload, dict) or set(payload) != {"format", "entries"} or type(payload.get("format")) is not int or payload.get("format") != 1 or not isinstance(payload.get("entries"), list):
        return (), "receipt_chain_schema_invalid"
    rows = payload["entries"]
    if len(rows) > MAX_RECEIPT_CHAIN_ENTRIES:
        return (), "receipt_chain_too_large"
    entries = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"index", "previous_digest", "receipt_digest", "chain_digest"}:
            return (), "receipt_chain_entry_schema_invalid"
        if type(row["index"]) is not int or any(not isinstance(row[k], str) for k in ("previous_digest", "receipt_digest", "chain_digest")):
            return (), "receipt_chain_entry_schema_invalid"
        entries.append(ReceiptChainEntry(row["index"], row["previous_digest"], row["receipt_digest"], row["chain_digest"]))
    ok, reason = verify_receipt_chain(tuple(entries))
    return (tuple(entries), "receipt_chain_imported") if ok else ((), "receipt_chain_rejected:" + reason)


@dataclass(frozen=True)
class ReceiptChainCheckpoint:
    entry_count: int
    head_digest: str
    checkpoint_digest: str


def create_receipt_chain_checkpoint(entries: Sequence[ReceiptChainEntry]) -> tuple[ReceiptChainCheckpoint | None, str]:
    """Seal the expected chain length/head so later truncation can be detected."""
    ok, reason = verify_receipt_chain(entries)
    if not ok:
        return None, reason
    head = entries[-1].chain_digest if entries else _ZERO
    payload = json.dumps({"entry_count": len(entries), "head_digest": head}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return ReceiptChainCheckpoint(len(entries), head, digest), "receipt_chain_checkpoint_created"


def verify_receipt_chain_checkpoint(entries: Sequence[ReceiptChainEntry], checkpoint: object) -> tuple[bool, str]:
    if not isinstance(checkpoint, ReceiptChainCheckpoint):
        return False, "receipt_chain_checkpoint_invalid"
    ok, reason = verify_receipt_chain(entries)
    if not ok:
        return False, reason
    if checkpoint.entry_count != len(entries):
        return False, "receipt_chain_checkpoint_length_mismatch"
    head = entries[-1].chain_digest if entries else _ZERO
    if checkpoint.head_digest != head:
        return False, "receipt_chain_checkpoint_head_mismatch"
    payload = json.dumps({"entry_count": checkpoint.entry_count, "head_digest": checkpoint.head_digest}, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != checkpoint.checkpoint_digest:
        return False, "receipt_chain_checkpoint_digest_mismatch"
    return True, "receipt_chain_checkpoint_verified"


def export_receipt_chain_checkpoint(checkpoint: ReceiptChainCheckpoint) -> str:
    """Serialize a validated checkpoint into canonical bounded JSON."""
    if not isinstance(checkpoint, ReceiptChainCheckpoint) or type(checkpoint.entry_count) is not int or checkpoint.entry_count < 0:
        raise ValueError("receipt_chain_checkpoint_invalid")
    if any(not isinstance(x, str) or len(x) != 64 or any(c not in "0123456789abcdef" for c in x) for x in (checkpoint.head_digest, checkpoint.checkpoint_digest)):
        raise ValueError("receipt_chain_checkpoint_invalid")
    payload = {"format": 1, "entry_count": checkpoint.entry_count, "head_digest": checkpoint.head_digest, "checkpoint_digest": checkpoint.checkpoint_digest}
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(text.encode("utf-8")) > 4096:
        raise ValueError("receipt_chain_checkpoint_too_large")
    return text


def import_receipt_chain_checkpoint(serialized: object) -> tuple[ReceiptChainCheckpoint | None, str]:
    if not isinstance(serialized, str):
        return None, "receipt_chain_checkpoint_serialization_invalid"
    if len(serialized.encode("utf-8")) > 4096:
        return None, "receipt_chain_checkpoint_serialization_too_large"
    try:
        payload = json.loads(serialized)
    except Exception:
        return None, "receipt_chain_checkpoint_json_invalid"
    if not isinstance(payload, dict) or set(payload) != {"format", "entry_count", "head_digest", "checkpoint_digest"} or type(payload.get("format")) is not int or payload.get("format") != 1:
        return None, "receipt_chain_checkpoint_schema_invalid"
    if type(payload.get("entry_count")) is not int or not 0 <= payload["entry_count"] <= MAX_RECEIPT_CHAIN_ENTRIES:
        return None, "receipt_chain_checkpoint_count_invalid"
    head, digest = payload.get("head_digest"), payload.get("checkpoint_digest")
    if any(not isinstance(x, str) or len(x) != 64 or any(c not in "0123456789abcdef" for c in x) for x in (head, digest)):
        return None, "receipt_chain_checkpoint_digest_invalid"
    cp = ReceiptChainCheckpoint(payload["entry_count"], head, digest)
    expected_payload = json.dumps({"entry_count": cp.entry_count, "head_digest": cp.head_digest}, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(expected_payload.encode("utf-8")).hexdigest() != cp.checkpoint_digest:
        return None, "receipt_chain_checkpoint_digest_mismatch"
    return cp, "receipt_chain_checkpoint_imported"
