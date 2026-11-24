"""Durable local conversation history for Alice.

Conversation history survives process shutdown and is stored locally under
alice_workspace. Credentials are never persisted by this component.
"""
from __future__ import annotations
import json, re, threading, time, uuid
from pathlib import Path
from ..knowledge.security import redact_secrets

_SECRET = re.compile(r"(?i)(api[\s_-]?key|token|password|secret|authorization|credential)\s*[:=]\s*\S+")

class PersistentConversation:
    def __init__(self, root=None, max_turns=50000):
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.dir = self.root / "alice_workspace" / "conversations"
        self.path = self.dir / "history.jsonl"
        self.meta = self.dir / "session.json"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_turns = max(100, int(max_turns))
        self._lock = threading.RLock()
        self.session_id = self._load_session()

    def _load_session(self):
        try:
            data = json.loads(self.meta.read_text(encoding="utf-8"))
            return str(data.get("session_id")) or uuid.uuid4().hex
        except Exception:
            sid = uuid.uuid4().hex
            self._save_session(sid)
            return sid

    def _save_session(self, sid):
        tmp = self.meta.with_suffix(".tmp")
        tmp.write_text(json.dumps({"session_id": sid, "updated_at": time.time()}, indent=2), encoding="utf-8")
        tmp.replace(self.meta)

    @staticmethod
    def _clean(text):
        text, _ = redact_secrets(str(text))
        text = _SECRET.sub(lambda m: m.group(0).split("=", 1)[0] + "=[REDACTED]" if "=" in m.group(0) else "[REDACTED]", text)
        return text[:20000]

    def append(self, role, content, **meta):
        row = {"id": uuid.uuid4().hex, "session_id": self.session_id,
               "time": time.time(), "role": str(role), "content": self._clean(content)}
        for k, v in meta.items():
            if k.lower() in {"api_key", "token", "password", "secret", "authorization", "credential"}:
                continue
            row[k] = self._clean(v) if isinstance(v, str) else v
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        self._save_session(self.session_id)
        return row

    def recent(self, limit=24):
        if not self.path.exists():
            return []
        with self._lock:
            rows = []
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
            return rows[-max(1, int(limit)):]

    def all(self):
        return self.recent(self.max_turns)

    def prompt_context(self, limit=12, max_chars=12000):
        rows = self.recent(limit)
        lines = []
        for row in rows:
            role = row.get("role", "unknown").upper()
            content = str(row.get("content", "")).strip()
            if content:
                lines.append(f"{role}: {content}")
        text = "\n".join(lines)
        return text[-max_chars:]

    def clear_session(self):
        with self._lock:
            self.session_id = uuid.uuid4().hex
            self._save_session(self.session_id)

    def compact(self):
        """Bound the JSONL file while retaining the newest history."""
        with self._lock:
            rows = self.all()
            tmp = self.path.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            tmp.replace(self.path)
