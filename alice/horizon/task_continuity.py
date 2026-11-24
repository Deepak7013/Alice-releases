"""ALICE v4.4 persistent executive task continuity contract.

Stores bounded, non-secret task checkpoints and produces a resume decision after
restart. It never executes a task or marks work complete. Persistence is atomic;
corrupt stores are preserved and made read-only rather than silently overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import uuid


@dataclass(frozen=True)
class ResumeDecision:
    task_id: str
    resumable: bool
    checkpoint: dict | None
    reason: str


class TaskContinuityStore:
    VERSION = "v4.4.0"
    VALID = {"active", "paused", "completed", "failed", "cancelled"}
    TERMINAL = {"completed", "failed", "cancelled"}
    MAX_STORE_BYTES = 2 * 1024 * 1024
    MAX_CHECKPOINT_STATE_BYTES = 64 * 1024
    MAX_OBJECTIVE_CHARS = 2000
    MAX_NEXT_ACTION_CHARS = 1000
    MAX_DEPENDENCIES = 32
    MAX_CHECKPOINTS = 16

    def __init__(self, root, max_tasks=64):
        self.root = Path(root).resolve()
        self.path = self.root / "alice_workspace" / "executive_tasks.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_tasks = max(1, int(max_tasks))
        self.tasks: dict[str, dict] = {}
        self.load_error: str | None = None
        self._load()

    @staticmethod
    def _json_bytes(value) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")

    def _load(self):
        if not self.path.exists():
            return
        try:
            if self.path.stat().st_size > self.MAX_STORE_BYTES:
                raise ValueError("task_store_too_large")
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or len(raw) > self.max_tasks:
                raise ValueError("task_store_schema_invalid")
            validated = {}
            for key, row in raw.items():
                if not isinstance(key, str) or not isinstance(row, dict):
                    raise ValueError("task_store_schema_invalid")
                if row.get("task_id") != key or row.get("status") not in self.VALID:
                    raise ValueError("task_store_schema_invalid")
                if not isinstance(row.get("objective"), str) or not row["objective"].strip():
                    raise ValueError("task_store_schema_invalid")
                if not isinstance(row.get("next_action", ""), str):
                    raise ValueError("task_store_schema_invalid")
                if not isinstance(row.get("dependencies", []), list) or len(row.get("dependencies", [])) > self.MAX_DEPENDENCIES:
                    raise ValueError("task_store_schema_invalid")
                checkpoints = row.get("checkpoints", [])
                if not isinstance(checkpoints, list) or len(checkpoints) > self.MAX_CHECKPOINTS:
                    raise ValueError("task_store_schema_invalid")
                # Reject non-JSON data and oversized task rows before they enter memory.
                if len(self._json_bytes(row)) > self.MAX_STORE_BYTES:
                    raise ValueError("task_record_too_large")
                validated[key] = row
            self.tasks = validated
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            # Never turn a damaged persistence file into an empty writable store.
            self.tasks = {}
            self.load_error = str(exc)[:120] or "task_store_invalid"

    def _save(self):
        if self.load_error:
            raise RuntimeError("task_store_read_only_after_load_error:" + self.load_error)
        rows = dict(self.tasks)
        if len(rows) > self.max_tasks:
            terminal = sorted(
                (row for row in rows.values() if row.get("status") in self.TERMINAL),
                key=lambda row: float(row.get("updated_at", 0)),
            )
            for row in terminal:
                if len(rows) <= self.max_tasks:
                    break
                rows.pop(row.get("task_id"), None)
            if len(rows) > self.max_tasks:
                raise ValueError("active_task_capacity_reached")
        payload = self._json_bytes(rows) + b"\n"
        if len(payload) > self.MAX_STORE_BYTES:
            raise ValueError("task_store_too_large")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb", dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp", delete=False
            ) as output:
                temporary = Path(output.name)
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            temporary = None
            # Best-effort directory durability on platforms that expose directory fsync.
            try:
                fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            except (OSError, AttributeError):
                pass
            self.tasks = rows
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def create(self, objective, *, next_action="", dependencies=None):
        objective = str(objective).strip()
        if not objective:
            raise ValueError("objective is required")
        if self.load_error:
            raise RuntimeError("task_store_read_only_after_load_error:" + self.load_error)
        task_id = "et_" + uuid.uuid4().hex[:16]
        self.tasks[task_id] = {
            "task_id": task_id, "objective": objective[:self.MAX_OBJECTIVE_CHARS], "status": "active",
            "next_action": str(next_action).strip()[:self.MAX_NEXT_ACTION_CHARS],
            "dependencies": [str(x).strip()[:500] for x in (dependencies or []) if str(x).strip()][:self.MAX_DEPENDENCIES],
            "checkpoints": [], "updated_at": time.time()
        }
        try:
            self._save()
        except Exception:
            self.tasks.pop(task_id, None)
            raise
        return self.get(task_id)

    def get(self, task_id):
        row = self.tasks.get(str(task_id))
        return dict(row) if row else None

    @staticmethod
    def _checkpoint_digest(task_id, checkpoint):
        payload = {key: checkpoint.get(key) for key in ("id", "label", "state", "verified", "at")}
        canonical = json.dumps({"task_id": str(task_id), "checkpoint": payload},
                               sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def checkpoint(self, task_id, *, label, state, verified=False):
        if self.load_error:
            raise RuntimeError("task_store_read_only_after_load_error:" + self.load_error)
        row = self.tasks.get(str(task_id))
        if not row:
            raise KeyError(str(task_id))
        if row.get("status") in {"completed", "cancelled", "failed"}:
            raise ValueError("task is not resumable")
        safe_state = dict(state or {})
        state_bytes = self._json_bytes(safe_state)
        if len(state_bytes) > self.MAX_CHECKPOINT_STATE_BYTES:
            raise ValueError("checkpoint_state_too_large")
        cp = {"id": uuid.uuid4().hex[:12], "label": str(label)[:200],
              "state": safe_state, "verified": bool(verified), "at": time.time()}
        cp["integrity_sha256"] = self._checkpoint_digest(task_id, cp)
        old_checkpoints = row["checkpoints"]
        old_updated = row["updated_at"]
        row["checkpoints"] = (old_checkpoints + [cp])[-self.MAX_CHECKPOINTS:]
        row["updated_at"] = time.time()
        try:
            self._save()
        except Exception:
            row["checkpoints"] = old_checkpoints
            row["updated_at"] = old_updated
            raise
        return cp

    def set_status(self, task_id, status, *, next_action=None):
        if status not in self.VALID:
            raise ValueError("invalid task status")
        if self.load_error:
            raise RuntimeError("task_store_read_only_after_load_error:" + self.load_error)
        row = self.tasks.get(str(task_id))
        if not row:
            raise KeyError(str(task_id))
        old_status, old_action, old_updated = row["status"], row.get("next_action", ""), row["updated_at"]
        row["status"] = status
        if next_action is not None:
            row["next_action"] = str(next_action)[:self.MAX_NEXT_ACTION_CHARS]
        row["updated_at"] = time.time()
        try:
            self._save()
        except Exception:
            row["status"], row["next_action"], row["updated_at"] = old_status, old_action, old_updated
            raise
        return self.get(task_id)

    def resume(self, task_id):
        row = self.tasks.get(str(task_id))
        if not row:
            if self.load_error:
                return ResumeDecision(str(task_id), False, None, "task_store_unreadable")
            raise KeyError(str(task_id))
        if row.get("status") in self.TERMINAL:
            return ResumeDecision(str(task_id), False, None, "task_not_active")
        candidates = [x for x in row.get("checkpoints", [])
                      if isinstance(x, dict) and x.get("verified") is True]
        verified = [x for x in candidates
                    if isinstance(x.get("integrity_sha256"), str)
                    and x.get("integrity_sha256") == self._checkpoint_digest(task_id, x)]
        if not verified:
            reason = "no_valid_verified_checkpoint" if candidates else "no_verified_checkpoint"
            return ResumeDecision(str(task_id), False, None, reason)
        return ResumeDecision(str(task_id), True, verified[-1], "verified_checkpoint_available")
