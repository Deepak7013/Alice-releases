from __future__ import annotations

import time
from datetime import datetime, time as day_time, timedelta

from .models import EmailStatus

class ApprovalRequired(PermissionError):
    """Raised when sending email requires explicit user approval."""

class EmailService:
    """Email workflow with a strict boundary between local drafts and delivery.

    ``provider`` may implement both ``send(draft)`` and the optional read-only
    ``count_received(start, end)`` operation. No mailbox is contacted unless a
    provider is explicitly injected.
    """
    def __init__(self, store, approval=None, provider=None):
        self.store=store
        self.approval=approval
        self.provider=provider

    def draft(self, **kwargs):
        return self.store.create_draft(**kwargs)

    def preview(self, draft_id):
        return self.store.get_draft(draft_id)

    def send(self, draft_id):
        draft=self.store.get_draft(draft_id)
        if self.approval is None:
            raise ApprovalRequired("Sending email requires explicit approval")
        decision=self.approval(draft)
        if isinstance(decision,dict): decision=decision.get("status") == "ok"
        if not decision: raise ApprovalRequired("Email send was not approved")
        if self.provider is None:
            # Approval records intent but cannot pretend delivery occurred.
            return self.store.record_message(draft, status=EmailStatus.QUEUED)
        result=self.provider.send(draft)
        if not result: raise RuntimeError("email provider rejected delivery")
        return self.store.record_message(draft, status=EmailStatus.SENT, sent_at=time.time())

    def cancel(self, draft_id):
        return self.store.cancel_draft(draft_id)

    def count_received(self, start: datetime, end: datetime):
        """Return a bounded count for [start, end), without reading message bodies."""
        if (self.provider is None
                or not callable(getattr(self.provider, "count_received", None))
                or not bool(getattr(self.provider, "configured", True))):
            return {
                "ok": False,
                "status": "not_configured",
                "message": "No read-only email account is connected. No mailbox was accessed.",
            }
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            raise TypeError("start and end must be datetime values")
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("start/end must be timezone-aware and end must be after start")

        raw = self.provider.count_received(start, end)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise ValueError("email provider returned an invalid count")
        return {
            "ok": True,
            "status": "observed",
            "count": raw,
            "start": start.isoformat(),
            "end_exclusive": end.isoformat(),
            "source": str(getattr(self.provider, "source_name", "connected email provider"))[:80],
            "message_bodies_read": False,
        }

    def count_received_today(self, now: datetime | None = None):
        """Count messages since local midnight; provider work remains read-only."""
        now = now or datetime.now().astimezone()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        start = datetime.combine(now.date(), day_time.min, tzinfo=now.tzinfo)
        end = start + timedelta(days=1)
        return self.count_received(start, end)
