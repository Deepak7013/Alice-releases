"""Append-only, hash-chained persistence for execution receipts.

This journal stores evidence; it does not authorize actions or make retries
idempotent. A damaged final record is treated as an incomplete tail and is
excluded from reads. Corruption in the middle of the chain is reported.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_GENESIS = "0" * 64
_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


class ReceiptJournalError(RuntimeError):
    """Raised when persisted receipt history is inconsistent."""


class ReceiptJournal:
    def __init__(self, path: str | os.PathLike[str], *, max_record_bytes: int = 1_048_576):
        if isinstance(max_record_bytes, bool) or not isinstance(max_record_bytes, int) or max_record_bytes < 256:
            raise ValueError("max_record_bytes must be an integer of at least 256")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_record_bytes = max_record_bytes
        # Instances targeting the same journal must serialize in-process too.
        # Windows byte-range locks coordinate processes but do not reliably
        # serialize separate file handles owned by threads in one process.
        lock_key = os.path.normcase(str(self.path.resolve()))
        with _PATH_LOCKS_GUARD:
            self._lock = _PATH_LOCKS.setdefault(lock_key, threading.RLock())
        self.claims_path = self.path.with_name(self.path.name + ".claims")
        self.claims_path.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    @contextmanager
    def _process_lock(self):
        """Serialize journal read/modify/replace operations across processes."""
        with self.lock_path.open("a+b") as stream:
            if os.name == "nt":
                import msvcrt
                # Avoid reading the byte protected by another process's
                # Windows range lock; that can raise PermissionError before
                # this process reaches its blocking lock acquisition.
                if self.lock_path.stat().st_size == 0:
                    stream.seek(0, os.SEEK_END)
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _canonical(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")

    def _read_valid(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        previous = _GENESIS
        raw_lines = self.path.read_bytes().splitlines(keepends=True)
        for index, raw_line in enumerate(raw_lines):
            is_final = index == len(raw_lines) - 1
            is_terminated = raw_line.endswith((b"\n", b"\r"))
            raw = raw_line.rstrip(b"\r\n")
            try:
                if len(raw) > self.max_record_bytes:
                    raise ValueError("record exceeds configured size limit")
                envelope = json.loads(raw.decode("utf-8"))
                if not isinstance(envelope, dict) or set(envelope) != {"previous_hash", "receipt", "record_hash"}:
                    raise ValueError("invalid journal envelope")
                payload = envelope["receipt"]
                if not isinstance(payload, dict):
                    raise ValueError("receipt must be an object")
                self._validate_receipt(payload)
                if envelope.get("previous_hash") != previous:
                    raise ValueError("previous hash mismatch")
                digest = hashlib.sha256(previous.encode("ascii") + self._canonical(payload)).hexdigest()
                if envelope.get("record_hash") != digest:
                    raise ValueError("record hash mismatch")
            except Exception as exc:
                # Only an unterminated final line is treated as a torn write.
                # A complete malformed final record is corruption, not recovery.
                if is_final and not is_terminated:
                    break
                raise ReceiptJournalError(f"receipt journal corruption at line {index + 1}") from exc
            records.append(payload)
            previous = digest
        return records

    def list(self) -> list[dict[str, Any]]:
        with self._lock, self._process_lock():
            return [dict(item) for item in self._read_valid()]

    def claim_action(self, action_id: str, tool: str) -> bool:
        """Durably claim an action ID before invoking its external side effect.

        The process lock prevents readers from observing the claim between
        exclusive creation and completion of its durable write. O_EXCL makes
        competing processes race-safe. Claims are intentionally not expired.
        """
        if not isinstance(action_id, str) or not action_id.strip():
            raise ValueError("action_id must be a non-empty string")
        if not isinstance(tool, str) or not tool.strip():
            raise ValueError("tool must be a non-empty string")
        token = hashlib.sha256(action_id.encode("utf-8")).hexdigest()
        claim_path = self.claims_path / (token + ".json")
        payload = {"action_id": action_id, "tool": tool, "claimed_at": time.time()}
        encoded = self._canonical(payload)
        if len(encoded) > self.max_record_bytes:
            raise ValueError("action claim exceeds configured size limit")
        with self._lock, self._process_lock():
            try:
                fd = os.open(claim_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                return False
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Persist the directory entry as well as the claim contents.
                if os.name != "nt":
                    directory_fd = os.open(self.claims_path, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
            except Exception:
                # Preserve the claim if its durability is uncertain.
                raise
            return True

    def get_action_claim(self, action_id: str) -> dict[str, Any] | None:
        """Return durable claim metadata for recovery/operator inspection."""
        if not isinstance(action_id, str) or not action_id.strip():
            raise ValueError("action_id must be a non-empty string")
        token = hashlib.sha256(action_id.encode("utf-8")).hexdigest()
        claim_path = self.claims_path / (token + ".json")
        with self._lock, self._process_lock():
            try:
                raw = claim_path.read_bytes()
            except FileNotFoundError:
                return None
            if len(raw) > self.max_record_bytes:
                raise ReceiptJournalError("action claim exceeds configured size limit")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ReceiptJournalError("action claim is corrupt") from exc
            if (
                not isinstance(payload, dict)
                or set(payload) != {"action_id", "tool", "claimed_at"}
                or payload.get("action_id") != action_id
                or not isinstance(payload.get("tool"), str)
                or not payload["tool"].strip()
                or isinstance(payload.get("claimed_at"), bool)
                or not isinstance(payload.get("claimed_at"), (int, float))
                or not math.isfinite(payload["claimed_at"])
                or payload["claimed_at"] <= 0
            ):
                raise ReceiptJournalError("action claim is corrupt")
            return dict(payload)

    @staticmethod
    def _validate_receipt(payload: dict[str, Any]) -> None:
        required = {"action_id", "tool", "admitted", "execution_ok", "verified", "outcome"}
        allowed = required | {"evidence"}
        if not required.issubset(payload) or not set(payload).issubset(allowed):
            raise ValueError("receipt has missing or unexpected fields")
        for field, limit in (("action_id", 512), ("tool", 512), ("outcome", 128)):
            value = payload[field]
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
                raise ValueError(f"receipt {field} is invalid")
        if any(type(payload[field]) is not bool for field in ("admitted", "execution_ok", "verified")):
            raise ValueError("receipt flags must be booleans")
        if payload["verified"] and not payload["execution_ok"]:
            raise ValueError("verified receipt requires execution success")
        if payload["execution_ok"] and not payload["admitted"]:
            raise ValueError("successful receipt requires admission")
        evidence = payload.get("evidence", "")
        if not isinstance(evidence, str) or len(evidence) > 4096:
            raise ValueError("receipt evidence is invalid")

    def append(self, receipt: Any) -> dict[str, Any]:
        payload = dict(receipt) if isinstance(receipt, dict) else dict(vars(receipt))
        # Validate JSON safety and the configured byte ceiling before schema
        # checks so oversized payloads consistently report the size violation.
        canonical = self._canonical(payload)
        if len(canonical) > self.max_record_bytes:
            raise ValueError("receipt exceeds configured size limit")
        self._validate_receipt(payload)
        with self._lock, self._process_lock():
            records = self._read_valid()
            action_id = str(payload["action_id"])
            if any(str(row.get("action_id")) == action_id for row in records):
                raise ValueError(f"duplicate action_id: {action_id}")
            # Rewrite the validated prefix to a temporary file before appending.
            # This also removes a torn final line left by a power loss/crash.
            previous = _GENESIS
            temp_path = self.path.with_name(self.path.name + ".tmp")
            with temp_path.open("wb") as stream:
                for row in records:
                    row_bytes = self._canonical(row)
                    row_hash = hashlib.sha256(previous.encode("ascii") + row_bytes).hexdigest()
                    envelope = {"previous_hash": previous, "receipt": row, "record_hash": row_hash}
                    encoded_row = self._canonical(envelope)
                    if len(encoded_row) > self.max_record_bytes:
                        raise ReceiptJournalError("existing receipt exceeds configured size limit")
                    stream.write(encoded_row + b"\n")
                    previous = row_hash
                digest = hashlib.sha256(previous.encode("ascii") + canonical).hexdigest()
                envelope = {"previous_hash": previous, "receipt": payload, "record_hash": digest}
                encoded = self._canonical(envelope)
                if len(encoded) > self.max_record_bytes:
                    raise ValueError("journal record exceeds configured size limit")
                stream.write(encoded + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.path)
            # Persist the directory entry where supported. Windows does not
            # expose a portable directory-fsync operation, so file fsync and
            # atomic replace remain the cross-platform baseline.
            if os.name != "nt":
                try:
                    directory_fd = os.open(self.path.parent, os.O_RDONLY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError:
                    pass
        return dict(payload)
