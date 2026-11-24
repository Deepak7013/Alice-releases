from __future__ import annotations
import json, re, time, uuid
from pathlib import Path
from .models import EmailDraft, EmailMessage, EmailStatus

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

class EmailStore:
    """Persistent local email state. It does not contact an email provider."""
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parents[2])
        self.path = self.root / "alice_workspace" / "email" / "state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict): raise ValueError
            raw.setdefault("drafts", {}); raw.setdefault("messages", {})
            return raw
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            return {"drafts": {}, "messages": {}}

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _addresses(values, field):
        values = list(values or [])
        if not values: raise ValueError(f"{field} requires at least one address")
        clean=[]
        for value in values:
            value=str(value).strip().lower()
            if not _EMAIL_RE.fullmatch(value): raise ValueError(f"invalid email address: {value}")
            if value not in clean: clean.append(value)
        return clean

    def create_draft(self, to, subject, body, cc=None, bcc=None, reply_to=None, thread_id=None, draft_id=None):
        to=self._addresses(to,"to"); cc=self._optional_addresses(cc,"cc"); bcc=self._optional_addresses(bcc,"bcc")
        if not str(subject).strip(): raise ValueError("subject is required")
        if not str(body).strip(): raise ValueError("body is required")
        if reply_to and not _EMAIL_RE.fullmatch(str(reply_to).strip().lower()): raise ValueError("invalid reply_to")
        draft_id=draft_id or uuid.uuid4().hex[:12]
        if not _ID_RE.fullmatch(draft_id) or draft_id in self.state["drafts"]: raise ValueError("invalid or duplicate draft_id")
        now=time.time(); draft=EmailDraft(draft_id,to,str(subject).strip(),str(body),cc,bcc,reply_to,thread_id,now,now)
        self.state["drafts"][draft_id]=draft.__dict__.copy(); self._save(); return draft

    def _optional_addresses(self, values, field):
        if not values: return []
        return self._addresses(values,field)

    def get_draft(self, draft_id):
        try: return EmailDraft(**self.state["drafts"][draft_id])
        except KeyError: raise KeyError(draft_id)

    def list_drafts(self):
        return sorted((EmailDraft(**x) for x in self.state["drafts"].values()), key=lambda x:x.updated_at, reverse=True)

    def cancel_draft(self, draft_id):
        if draft_id not in self.state["drafts"]: raise KeyError(draft_id)
        draft=self.state["drafts"].pop(draft_id); self._save(); return EmailDraft(**draft)

    def record_message(self, draft, status=EmailStatus.QUEUED, message_id=None, sent_at=None):
        message_id=message_id or uuid.uuid4().hex[:12]
        if not _ID_RE.fullmatch(message_id) or message_id in self.state["messages"]: raise ValueError("invalid or duplicate message_id")
        now=time.time(); msg=EmailMessage(message_id,draft.draft_id,status,draft.to,draft.subject,draft.body,draft.cc,draft.bcc,draft.thread_id,now,sent_at)
        self.state["messages"][message_id]=msg.__dict__.copy(); self.state["messages"][message_id]["status"]=status.value; self._save(); return msg

    def get_message(self, message_id):
        try:
            raw=dict(self.state["messages"][message_id]); raw["status"]=EmailStatus(raw["status"]); return EmailMessage(**raw)
        except KeyError: raise KeyError(message_id)
