from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class EmailStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    SENT = "sent"
    CANCELLED = "cancelled"

@dataclass
class EmailDraft:
    draft_id: str
    to: list[str]
    subject: str
    body: str
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    reply_to: Optional[str] = None
    thread_id: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0

@dataclass
class EmailMessage:
    message_id: str
    draft_id: str
    status: EmailStatus
    to: list[str]
    subject: str
    body: str
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    thread_id: Optional[str] = None
    created_at: float = 0.0
    sent_at: Optional[float] = None
