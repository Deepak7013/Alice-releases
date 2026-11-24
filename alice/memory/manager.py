from __future__ import annotations
import hashlib, json, re, sqlite3, time, uuid
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from pathlib import Path

@dataclass
class MemoryRecord:
    id: str
    kind: str
    key: str
    value: str
    confidence: float = 0.9
    status: str = "active"
    source: str = "user"
    created_at: float = 0.0
    updated_at: float = 0.0
    supersedes: str = ""

class MemoryManager:
    """Structured long-term memory with correction and explicit forgetting.

    This layer is intentionally deterministic and local. It complements the
    knowledge library instead of replacing it. Facts can be corrected or
    explicitly forgotten without deleting unrelated knowledge.
    """
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.path = self.root / "alice_workspace" / "library" / "alice_knowledge.sqlite3"
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
            c.execute("""CREATE TABLE IF NOT EXISTS memory_v2 (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, key TEXT NOT NULL,
                value TEXT NOT NULL, confidence REAL NOT NULL,
                status TEXT NOT NULL, source TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                supersedes TEXT NOT NULL DEFAULT ''
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_memory_v2_key ON memory_v2(key)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_memory_v2_status ON memory_v2(status)")

    @staticmethod
    def _norm(text):
        return " ".join(re.findall(r"[a-z0-9]+", str(text).lower()))

    def set(self, key, value, kind="fact", confidence=0.9, source="user", supersedes=""):
        key = str(key).strip()[:300]; value = str(value).strip()[:3000]
        if not key or not value:
            raise ValueError("memory key and value are required")
        now = time.time(); mid = uuid.uuid4().hex
        rec = MemoryRecord(mid, kind[:80], key, value, max(0.0,min(1.0,float(confidence))),
                           "active", source[:120], now, now, supersedes)
        with self._connect() as c:
            c.execute("INSERT INTO memory_v2 VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(asdict(rec).values()))
        return rec

    def list(self, query="", kind=None, limit=30):
        terms = [x for x in self._norm(query).split() if len(x) >= 2]
        where=["status='active'"]; params=[]
        if kind:
            where.append("kind=?"); params.append(str(kind))
        if terms:
            where.append("(" + " OR ".join(["lower(key) LIKE ? OR lower(value) LIKE ?"]*len(terms)) + ")")
            for t in terms: params += [f"%{t}%", f"%{t}%"]
        params.append(max(1,min(int(limit),100)))
        with self._connect() as c:
            rows=c.execute("SELECT * FROM memory_v2 WHERE " + " AND ".join(where) + " ORDER BY confidence DESC, updated_at DESC LIMIT ?", params).fetchall()
        return [MemoryRecord(**dict(r)) for r in rows]

    def forget(self, query, limit=10):
        query=str(query).strip()
        matches=[]
        # A short stable prefix lets the user target one exact record from the
        # memory listing without relying on an ambiguous natural-language query.
        if len(query) >= 8:
            with self._connect() as c:
                rows=c.execute(
                    "SELECT * FROM memory_v2 WHERE status='active' AND id LIKE ? LIMIT 2",
                    (query+"%",),
                ).fetchall()
            matches=[MemoryRecord(**dict(row)) for row in rows]
            if len(matches) > 1:
                return {"ok":False,"forgotten":0,"reason":"ambiguous_id",
                        "matches":[asdict(x) for x in matches]}
        if not matches:
            # Never bulk-delete fuzzy results. Return candidates so ALICE can
            # show their IDs and let the user choose a specific record.
            matches=self.list(query,limit=max(2,min(int(limit),100)))
            if len(matches) > 1:
                return {"ok":False,"forgotten":0,"reason":"ambiguous",
                        "matches":[asdict(x) for x in matches]}
        if not matches: return {"ok":False,"forgotten":0,"matches":[]}
        now=time.time()
        with self._connect() as c:
            for r in matches:
                c.execute("UPDATE memory_v2 SET status='forgotten', updated_at=? WHERE id=?", (now,r.id))
        return {"ok":True,"forgotten":len(matches),"matches":[asdict(x) for x in matches]}

    def correct(self, query, new_value, kind=None, source="user"):
        query=str(query).strip()
        old=[]
        if len(query) >= 8:
            with self._connect() as c:
                rows=c.execute(
                    "SELECT * FROM memory_v2 WHERE status='active' AND id LIKE ? LIMIT 2",
                    (query+"%",),
                ).fetchall()
            old=[MemoryRecord(**dict(row)) for row in rows]
            if kind:
                old=[record for record in old if record.kind == str(kind)]
        if not old:
            old=self.list(query,kind=kind,limit=2)
        if len(old) > 1:
            return {"ok":False,"reason":"Several memories match; choose one memory ID.",
                    "matches":[asdict(x) for x in old]}
        if not old:
            return {"ok":False,"reason":"No matching active memory found."}
        previous=old[0]
        self.forget(previous.id, limit=1)
        new=self.set(previous.key, new_value, kind=kind or previous.kind,
                     confidence=0.98, source=source, supersedes=previous.id)
        return {"ok":True,"previous":asdict(previous),"new":asdict(new)}

    def summary(self, limit=20):
        rows=self.list(limit=limit)
        if not rows: return "No structured long-term memories yet."
        return "\n".join(
            f"- [{r.kind}] {r.key}: {r.value} (id {r.id[:8]}, confidence {r.confidence:.2f})"
            for r in rows
        )

    def learn_explicit(self, text):
        """Learn only explicit durable statements; return number stored."""
        s=str(text).strip()
        patterns=[
            ("preference", re.compile(r"(?i)^my preference is\s+(.+)$")),
            ("preference", re.compile(r"(?i)^i (?:prefer|like|love|hate|don't like|do not like)\s+(.+)$")),
            ("instruction", re.compile(r"(?i)^(?:remember|from now on|going forward)\s*[:,-]?\s*(.+)$")),
            ("instruction", re.compile(r"(?i)^(?:during alice testing|for future alice upgrades)\b(.+)$")),
            ("fact", re.compile(r"(?i)^my (?:project|goal|device|laptop|phone|setup) is\s+(.+)$")),
        ]
        for kind, pat in patterns:
            m=pat.match(s)
            if m:
                value=m.group(1).strip()
                if kind == "instruction" and re.match(r"(?i)^(?:during alice testing|for future alice upgrades)\b", s):
                    value=s
                key=value[:120]
                # Avoid credential-shaped memory even if a user accidentally asks to remember it.
                if re.search(r"(?i)(api[_-]?key|password|secret|token|authorization)\s*[:=]", value):
                    return 0
                existing=self.list(key, kind=kind, limit=1)
                if existing and self._norm(existing[0].value)==self._norm(value): return 0
                self.set(key,value,kind=kind,confidence=0.96,source="explicit_chat")
                return 1
        return 0
