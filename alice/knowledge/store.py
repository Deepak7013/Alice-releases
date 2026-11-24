
from __future__ import annotations
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable
from .models import KnowledgeItem, SourceEvidence, ResearchSession, Claim


class KnowledgeStore:
    """Local persistent knowledge store.

    SQLite is used instead of a giant transcript so retrieval stays cheap and
    the knowledge layer can later swap in embeddings without changing callers.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def _init(self):
        with self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id TEXT PRIMARY KEY, topic TEXT NOT NULL, text TEXT NOT NULL,
                source_json TEXT NOT NULL, tags_json TEXT NOT NULL,
                confidence REAL NOT NULL, trusted INTEGER NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                content_hash TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON knowledge(topic);
            CREATE INDEX IF NOT EXISTS idx_knowledge_hash ON knowledge(content_hash);
            CREATE TABLE IF NOT EXISTS research (
                id TEXT PRIMARY KEY, question TEXT NOT NULL, status TEXT NOT NULL,
                source_ids_json TEXT NOT NULL, claims_json TEXT NOT NULL,
                conclusion TEXT NOT NULL, created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """)

    def add(self, item: KnowledgeItem) -> str:
        with self._connect() as c:
            c.execute(
                """INSERT OR REPLACE INTO knowledge
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item.id, item.topic, item.text, json.dumps(item.source.__dict__),
                 json.dumps(item.tags), float(item.confidence), int(item.trusted),
                 item.created_at, item.updated_at, item.content_hash)
            )
        return item.id

    def create(self, topic: str, text: str, source: SourceEvidence,
               tags: Iterable[str] = (), confidence: float = 0.5,
               trusted: bool = False) -> KnowledgeItem:
        item = KnowledgeItem(
            id=uuid.uuid4().hex,
            topic=topic[:200],
            text=text,
            source=source,
            tags=list(tags)[:50],
            confidence=max(0.0, min(1.0, float(confidence))),
            trusted=bool(trusted),
        )
        self.add(item)
        return item

    def get(self, item_id: str) -> KnowledgeItem | None:
        with self._connect() as c:
            row = c.execute("SELECT * FROM knowledge WHERE id=?", (item_id,)).fetchone()
        if not row:
            return None
        return self._row_item(row)

    def _row_item(self, row) -> KnowledgeItem:
        return KnowledgeItem(
            id=row["id"], topic=row["topic"], text=row["text"],
            source=SourceEvidence(**json.loads(row["source_json"])),
            tags=json.loads(row["tags_json"]),
            confidence=row["confidence"], trusted=bool(row["trusted"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
            content_hash=row["content_hash"],
        )

    def search(self, query: str, topic: str | None = None, limit: int = 10,
               trusted_only: bool = False) -> list[KnowledgeItem]:
        terms = [x.lower() for x in query.split() if len(x) >= 2][:12]
        if not terms:
            return []
        clauses = []
        params: list[object] = []
        for term in terms:
            clauses.append("(lower(topic) LIKE ? OR lower(text) LIKE ? OR lower(tags_json) LIKE ?)")
            like = f"%{term}%"
            params.extend([like, like, like])
        where = " OR ".join(clauses)
        if topic:
            where = f"({where}) AND topic=?"
            params.append(topic)
        if trusted_only:
            where += " AND trusted=1"
        params.append(max(1, min(int(limit), 100)))
        with self._connect() as c:
            rows = c.execute(
                f"SELECT * FROM knowledge WHERE {where} ORDER BY confidence DESC, updated_at DESC LIMIT ?",
                params
            ).fetchall()
        return [self._row_item(r) for r in rows]

    def duplicate_by_hash(self, content_hash: str) -> KnowledgeItem | None:
        with self._connect() as c:
            row = c.execute(
                "SELECT * FROM knowledge WHERE content_hash=? LIMIT 1", (content_hash,)
            ).fetchone()
        return self._row_item(row) if row else None

    def save_research(self, session: ResearchSession):
        session.updated_at = time.time()
        with self._connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO research VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session.id, session.question, session.status,
                 json.dumps(session.source_ids), json.dumps([x.__dict__ for x in session.claims]),
                 session.conclusion, session.created_at, session.updated_at)
            )

    def get_research(self, session_id: str) -> ResearchSession | None:
        with self._connect() as c:
            row = c.execute("SELECT * FROM research WHERE id=?", (session_id,)).fetchone()
        if not row:
            return None
        return ResearchSession(
            id=row["id"], question=row["question"], status=row["status"],
            source_ids=json.loads(row["source_ids_json"]),
            claims=[Claim(**x) for x in json.loads(row["claims_json"])],
            conclusion=row["conclusion"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
