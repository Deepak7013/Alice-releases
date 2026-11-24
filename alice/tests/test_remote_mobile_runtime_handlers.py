from types import SimpleNamespace

import pytest

from alice.remote.mobile_link import RemoteMobilePolicyError, authorize_remote_mobile_command
from alice.remote.runtime_handlers import (
    MAX_REMOTE_MESSAGE_CHARS,
    MAX_REMOTE_REPLY_CHARS,
    build_remote_mobile_handlers,
)


def test_remote_chat_uses_only_text_response_api():
    calls = []

    def respond_text(message, *, concise):
        calls.append((message, concise))
        return "safe answer"

    agent = SimpleNamespace(respond_text=respond_text, run=lambda _message: pytest.fail("tool path invoked"))
    handler = build_remote_mobile_handlers(agent)["alice.chat"]
    assert handler({"message": "  hello Alice  "}) == {"text": "safe answer"}
    assert calls == [("hello Alice", False)]


def test_remote_chat_rejects_missing_or_oversized_messages():
    handler = build_remote_mobile_handlers(SimpleNamespace(respond_text=lambda *_a, **_k: "ok"))["alice.chat"]
    with pytest.raises(ValueError, match="non-empty"):
        handler({"message": "  "})
    with pytest.raises(ValueError, match="limit"):
        handler({"message": "x" * (MAX_REMOTE_MESSAGE_CHARS + 1)})


def test_remote_chat_bounds_reply_and_never_falls_back_to_run():
    agent = SimpleNamespace(respond_text=lambda *_a, **_k: "r" * (MAX_REMOTE_REPLY_CHARS + 500),
                            run=lambda _message: pytest.fail("tool path invoked"))
    result = build_remote_mobile_handlers(agent)["alice.chat"]({"message": "hi"})
    assert len(result["text"]) == MAX_REMOTE_REPLY_CHARS


def test_remote_status_exposes_only_allowlisted_scalar_fields():
    handlers = build_remote_mobile_handlers(
        SimpleNamespace(respond_text=lambda *_a, **_k: "ok"),
        status_provider=lambda: {
            "version": "5.0-dev",
            "state": "ready",
            "provider": "openrouter",
            "api_key": "must-not-leak",
            "conversation": ["private text"],
        },
    )
    assert handlers["alice.status.read"]({}) == {
        "version": "5.0-dev",
        "state": "ready",
        "provider": "openrouter",
    }


def test_remote_chat_requires_explicit_chat_scope():
    assert authorize_remote_mobile_command("alice.chat", frozenset({"chat"})) == "chat"
    with pytest.raises(RemoteMobilePolicyError):
        authorize_remote_mobile_command("alice.chat", frozenset({"status.read"}))


def test_remote_email_count_requires_email_scope_and_returns_only_count_metadata():
    class EmailService:
        def count_received_today(self):
            return {"ok": True, "status": "observed", "count": 7,
                    "start": "2026-10-22T00:00:00+05:30", "end_exclusive": "2026-10-23T00:00:00+05:30",
                    "message_bodies_read": False, "message_ids": ["must-not-leak"]}

    assert authorize_remote_mobile_command("email.count_today", frozenset({"email.read"})) == "email.read"
    with pytest.raises(RemoteMobilePolicyError):
        authorize_remote_mobile_command("email.count_today", frozenset({"chat"}))
    handler = build_remote_mobile_handlers(
        SimpleNamespace(respond_text=lambda *_a, **_k: "ok"), email_service=EmailService()
    )["email.count_today"]
    assert handler({}) == {"ok": True, "status": "observed", "count": 7,
                          "start": "2026-10-22T00:00:00+05:30",
                          "end_exclusive": "2026-10-23T00:00:00+05:30",
                          "message_bodies_read": False}


def test_remote_email_count_reports_unconfigured_without_mailbox_request():
    class EmailService:
        def count_received_today(self):
            return {"ok": False, "status": "not_configured",
                    "message": "No read-only email account is connected. No mailbox was accessed."}

    handler = build_remote_mobile_handlers(
        SimpleNamespace(respond_text=lambda *_a, **_k: "ok"), email_service=EmailService()
    )["email.count_today"]
    assert handler({}) == {"ok": False, "status": "not_configured",
                          "message": "No read-only email account is connected. No mailbox was accessed."}


def test_remote_email_draft_uses_text_brain_and_never_sends():
    calls = []

    class EmailService:
        def draft(self, **fields):
            calls.append(("save", fields))
            return SimpleNamespace(draft_id="draft-123", to=fields["to"],
                                   subject=fields["subject"], body=fields["body"])

    def respond_text(prompt, *, concise):
        calls.append(("model", prompt, concise))
        return "Hello, this is the requested draft."

    handler = build_remote_mobile_handlers(
        SimpleNamespace(respond_text=respond_text, run=lambda *_a: pytest.fail("tool path invoked")),
        email_service=EmailService(),
    )["email.draft.create"]
    result = handler({"to": "User@example.com", "subject": "Schedule",
                      "instructions": "Ask to meet next week."})
    assert result == {"ok": True, "status": "draft_created", "draft_id": "draft-123",
                      "to": ["User@example.com"], "subject": "Schedule",
                      "body": "Hello, this is the requested draft.", "delivery": "not_sent"}
    assert calls[0][0] == "model" and calls[0][2] is False
    assert calls[1][0] == "save" and calls[1][1]["body"] == result["body"]
    assert "send" in calls[0][1].lower()
    assert authorize_remote_mobile_command("email.draft.create", frozenset({"email.draft"})) == "email.draft"
    with pytest.raises(RemoteMobilePolicyError):
        authorize_remote_mobile_command("email.draft.create", frozenset({"chat"}))


def test_remote_email_draft_validates_inputs_before_model_or_storage():
    calls = []
    handler = build_remote_mobile_handlers(
        SimpleNamespace(respond_text=lambda *_a, **_k: calls.append("model") or "draft"),
        email_service=SimpleNamespace(draft=lambda **_k: calls.append("save")),
    )["email.draft.create"]
    with pytest.raises(ValueError, match="recipient"):
        handler({"to": "", "subject": "Hi", "instructions": "Please write"})
    with pytest.raises(ValueError, match="3000"):
        handler({"to": "a@example.com", "subject": "Hi", "instructions": "x" * 3001})
    assert calls == []

