"""SQLite-backed persistent memory with thread-safe, bounded transactions.

Memory is advisory context only; authorization remains in the execution policy.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from .models import MemoryItem, MemoryKind, MemoryScope


class ContextMemory:
    """A small durable memory store safe for concurrent threads/processes.

    Each operation is serialized per instance. SQLite's busy timeout and WAL
    mode coordinate independent instances sharing the same database file.
    """

    def __init__(self, path="alice_context.db", *, timeout: float = 5.0):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a finite positive number")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number")
        self.path = str(path)
        self._lock = threading.RLock()
        parent = Path(self.path).parent
        if parent != Path("."):
            parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(
            self.path, timeout=float(timeout), check_same_thread=False,
            isolation_level="DEFERRED",
        )
        with self._lock:
            self.db.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
            # WAL is persistent for file-backed DBs; in-memory DBs report memory.
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("""CREATE TABLE IF NOT EXISTS memories(
                hash TEXT PRIMARY KEY, content TEXT NOT NULL, kind TEXT NOT NULL,
                scope TEXT NOT NULL, confidence REAL NOT NULL, source TEXT NOT NULL,
                tags TEXT NOT NULL, created REAL NOT NULL, confirmed REAL,
                expires REAL)""")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_memories_scope_expiry ON memories(scope, expires)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind)")
            self.db.commit()

    def add(self, item: MemoryItem):
        if not isinstance(item, MemoryItem):
            raise TypeError("item must be a MemoryItem")
        if not item.content or not item.content.strip():
            raise ValueError("memory content must not be empty")
        if not math.isfinite(float(item.confidence)) or not 0.0 <= float(item.confidence) <= 1.0:
            raise ValueError("memory confidence must be between 0 and 1")
        if item.expires_at is not None and not math.isfinite(float(item.expires_at)):
            raise ValueError("memory expiry must be finite")
        tags = json.dumps(list(item.tags), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            try:
                self.db.execute("""INSERT INTO memories
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(hash) DO UPDATE SET
                    content=excluded.content, kind=excluded.kind, scope=excluded.scope,
                    confidence=excluded.confidence, source=excluded.source,
                    tags=excluded.tags, confirmed=excluded.confirmed,
                    expires=excluded.expires""",
                    (item.content_hash, item.content, item.kind.value, item.scope.value,
                     float(item.confidence), item.source, tags, float(item.created_at),
                     float(item.last_confirmed_at), item.expires_at))
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
        return item.content_hash

    def get(self, content_hash):
        with self._lock:
            row = self.db.execute("SELECT * FROM memories WHERE hash=?", (content_hash,)).fetchone()
        return self._row(row) if row else None

    def list_active(self, scope: Optional[MemoryScope] = None):
        now = time.time()
        query = "SELECT * FROM memories WHERE expires IS NULL OR expires > ?"
        args = [now]
        if scope is not None:
            if not isinstance(scope, MemoryScope):
                raise TypeError("scope must be a MemoryScope")
            query += " AND scope=?"
            args.append(scope.value)
        query += " ORDER BY created DESC, hash ASC"
        with self._lock:
            rows = self.db.execute(query, args).fetchall()
        return [self._row(row) for row in rows]

    def confirm(self, content_hash, confidence=None):
        if confidence is not None:
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise TypeError("confidence must be numeric")
            if not math.isfinite(confidence):
                raise ValueError("confidence must be finite")
            confidence = max(0.0, min(1.0, float(confidence)))
        with self._lock:
            values = [time.time()]
            query = "UPDATE memories SET confirmed=?"
            if confidence is not None:
                query += ", confidence=?"
                values.append(confidence)
            query += " WHERE hash=?"
            values.append(content_hash)
            self.db.execute(query, values)
            self.db.commit()

    def close(self):
        with self._lock:
            if self.db is not None:
                self.db.close()
                self.db = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _row(self, row):
        try:
            tags = json.loads(row[6] or "[]")
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise ValueError("stored memory tags must be a list of strings")
            return MemoryItem(
                content=row[1], kind=MemoryKind(row[2]), scope=MemoryScope(row[3]),
                confidence=row[4], source=row[5], tags=tags,
                created_at=row[7], last_confirmed_at=row[8], expires_at=row[9])
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"invalid memory record {row[0]!r}: {exc}") from exc
