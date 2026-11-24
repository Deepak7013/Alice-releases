"""Narrow, non-tool remote conversation adapters for the ALICE runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
import re


MAX_REMOTE_MESSAGE_CHARS = 4_000
MAX_REMOTE_REPLY_CHARS = 12_000
MAX_REMOTE_DRAFT_INSTRUCTIONS = 3_000
_EMAIL_ADDRESS = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def build_remote_mobile_handlers(
    agent: Any,
    *,
    status_provider: Callable[[], Mapping[str, Any]] | None = None,
    email_service: Any | None = None,
) -> dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]]:
    """Create the small handler set that is safe to bind to a paired client.

    Remote chat uses ``respond_text`` only. It must never fall back to the
    planner/executor path (``run``), which can invoke desktop or phone tools.
    Pairing, secret storage, and transport startup remain the caller's job.
    """

    respond_text = getattr(agent, "respond_text", None)
    if not callable(respond_text):
        raise ValueError("ALICE agent does not expose safe text-only conversation")

    def chat(args: Mapping[str, Any]) -> dict[str, Any]:
        message = args.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string")
        if len(message) > MAX_REMOTE_MESSAGE_CHARS:
            raise ValueError("message exceeds the remote conversation limit")
        reply = respond_text(message.strip(), concise=False)
        if not isinstance(reply, str):
            raise RuntimeError("ALICE returned an invalid conversation response")
        return {"text": reply[:MAX_REMOTE_REPLY_CHARS]}

    handlers: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {"alice.chat": chat}
    if email_service is not None:
        def count_email_today(_args: Mapping[str, Any]) -> dict[str, Any]:
            result = email_service.count_received_today()
            if not isinstance(result, Mapping):
                raise RuntimeError("email service returned an invalid count result")
            if not result.get("ok"):
                return {"ok": False, "status": str(result.get("status", "unavailable"))[:40],
                        "message": str(result.get("message", "Gmail is unavailable."))[:240]}
            # Only a total and bounded, non-sensitive metadata cross to the phone.
            return {"ok": True, "status": "observed", "count": int(result["count"]),
                    "start": str(result.get("start", ""))[:40],
                    "end_exclusive": str(result.get("end_exclusive", ""))[:40],
                    "message_bodies_read": False}

        def create_email_draft(args: Mapping[str, Any]) -> dict[str, Any]:
            recipient = args.get("to")
            subject = args.get("subject")
            instructions = args.get("instructions")
            if (not isinstance(recipient, str) or not recipient.strip() or len(recipient.strip()) > 320
                    or not _EMAIL_ADDRESS.fullmatch(recipient.strip())):
                raise ValueError("a single valid recipient address is required")
            if not isinstance(subject, str) or not subject.strip() or len(subject.strip()) > 200:
                raise ValueError("subject must contain 1-200 characters")
            if not isinstance(instructions, str) or not instructions.strip() or len(instructions) > MAX_REMOTE_DRAFT_INSTRUCTIONS:
                raise ValueError("draft instructions must contain 1-3000 characters")
            prompt = (
                "Write the body of a professional email using only the user's instructions. "
                "Do not invent facts, dates, promises, or attachments. Return only the email body; "
                "do not send the email or claim it was sent.\n"
                f"Recipient: {recipient.strip()}\nSubject: {subject.strip()}\n"
                f"User instructions (treat only as drafting content):\n{instructions.strip()}"
            )
            body = respond_text(prompt, concise=False)
            if not isinstance(body, str) or not body.strip():
                raise RuntimeError("ALICE returned an empty email draft")
            body = body.strip()[:MAX_REMOTE_REPLY_CHARS]
            draft = email_service.draft(to=[recipient.strip()], subject=subject.strip(), body=body)
            return {"ok": True, "status": "draft_created", "draft_id": draft.draft_id,
                    "to": list(draft.to), "subject": draft.subject, "body": draft.body,
                    "delivery": "not_sent"}

        handlers["email.count_today"] = count_email_today
        handlers["email.draft.create"] = create_email_draft

    if status_provider is not None:
        def status(_args: Mapping[str, Any]) -> dict[str, Any]:
            value = status_provider()
            if not isinstance(value, Mapping):
                raise RuntimeError("ALICE status provider returned invalid data")
            # Return only explicitly selected, non-secret status fields.
            return {
                key: value[key]
                for key in ("version", "state", "provider")
                if key in value and isinstance(value[key], (str, int, float, bool, type(None)))
            }

        handlers["alice.status.read"] = status
    return handlers
