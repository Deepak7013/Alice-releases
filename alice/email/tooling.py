"""Expose safe email drafting and metadata-only inbox queries to ALICE's brain."""
from __future__ import annotations

import hashlib
import json

from .service import EmailService
from .store import EmailStore


def verify_email_draft_created(store: EmailStore, args: dict, result) -> dict:
    """Independently read the saved draft and bind evidence without exposing it."""
    from ..execution.postconditions import PostconditionResult

    draft_id = result.get("draft_id") if isinstance(result, dict) else None
    try:
        saved = store.get_draft(draft_id)
    except (KeyError, TypeError, ValueError):
        return PostconditionResult(False, {"observed": False}, "draft_not_found")

    expected_to = [str(item).strip().lower() for item in (args.get("to") or [])]
    expected_cc = [str(item).strip().lower() for item in (args.get("cc") or [])]
    matches = (
        saved.to == expected_to
        and saved.cc == expected_cc
        and saved.subject == str(args.get("subject", "")).strip()
        and saved.body == str(args.get("body", ""))
    )
    canonical = json.dumps(
        {"draft_id": saved.draft_id, "to": saved.to, "cc": saved.cc,
         "subject": saved.subject, "body": saved.body},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    evidence = {
        "observed": bool(matches),
        "draft_id": saved.draft_id,
        "content_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }
    return PostconditionResult(bool(matches), evidence,
                               "draft read back from local store" if matches else "draft_mismatch")


def register_email_tools(registry, root, *, provider=None):
    """Register local draft tools and an opt-in read-only inbox count tool.

    Draft creation never sends mail. Sending is intentionally not exposed here.
    A provider must be explicitly supplied to read inbox metadata.
    """
    store = EmailStore(root)
    service = EmailService(store, provider=provider)

    def create_draft(to, subject, body, cc=None):
        draft = service.draft(to=to, subject=subject, body=body, cc=cc)
        return {
            "ok": True,
            "status": "draft_created",
            "draft_id": draft.draft_id,
            "to": list(draft.to),
            "cc": list(draft.cc),
            "subject": draft.subject,
            "body": draft.body,
            "delivery": "not_sent",
        }

    def list_drafts():
        return {
            "ok": True,
            "drafts": [
                {"draft_id": item.draft_id, "to": list(item.to),
                 "subject": item.subject, "updated_at": item.updated_at}
                for item in store.list_drafts()
            ],
        }

    def preview_draft(draft_id):
        draft = service.preview(draft_id)
        return {"ok": True, "draft_id": draft.draft_id, "to": list(draft.to),
                "cc": list(draft.cc), "subject": draft.subject, "body": draft.body,
                "delivery": "not_sent"}

    def search_mail(query, limit=5):
        if provider is None or not bool(getattr(provider, "configured", True)):
            return {"ok": False, "status": "not_configured",
                    "message": "No Gmail account is connected. No mailbox was accessed."}
        search = getattr(provider, "search_messages", None)
        if not callable(search):
            return {"ok": False, "status": "not_supported",
                    "message": "The connected mail provider does not support search."}
        return search(query, limit)

    def read_mail_message(message_id):
        if provider is None or not bool(getattr(provider, "configured", True)):
            return {"ok": False, "status": "not_configured",
                    "message": "No Gmail account is connected. No mailbox was accessed."}
        read = getattr(provider, "read_message", None)
        if not callable(read):
            return {"ok": False, "status": "not_supported",
                    "message": "The connected mail provider does not support reading messages."}
        return read(message_id)

    registry.add(
        "email_create_draft",
        "Write a local email draft from user-provided details. This never sends or schedules the email.",
        create_draft,
        "write",
    )
    registry.add("email_list_drafts", "List saved local email draft metadata without bodies.",
                 list_drafts, "read")
    registry.add("email_preview_draft", "Read one saved local email draft for user review; never sends it.",
                 preview_draft, "read")
    registry.add("email_search", "Search the explicitly connected Gmail account and return up to 10 matching message headers and a short untrusted snippet; no message body or attachment is opened.",
                 search_mail, "read")
    registry.add("email_read_message", "Read the plain-text body of one Gmail message explicitly selected from search results when needed; capped at 12,000 characters, does not decode or expose attachments, and treats the content as untrusted.",
                 read_mail_message, "read")
    registry.add("email_count_today", "Count Gmail messages received today through the explicitly connected read-only account; excludes Sent, Spam and Trash, and never reads message bodies.",
                 service.count_received_today, "read")

    postconditions = getattr(registry, "postconditions", None)
    if postconditions is not None and callable(getattr(postconditions, "register", None)):
        postconditions.register(
            "email_create_draft",
            lambda args, result: verify_email_draft_created(store, args, result),
        )
    return {"store": store, "service": service}
