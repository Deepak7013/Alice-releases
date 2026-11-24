from datetime import datetime, timezone
from pathlib import Path

from alice.agent.executor import Executor
from alice.email.tooling import register_email_tools
from alice.execution.postconditions import PostconditionRegistry
from alice.tools.registry import ToolRegistry


def test_email_tooling_creates_a_local_draft_and_verifies_readback(tmp_path):
    tools = ToolRegistry()
    tools.postconditions = PostconditionRegistry()
    register_email_tools(tools, tmp_path)

    result = Executor(tools).run({
        "steps": [{
            "tool": "email_create_draft",
            "args": {"to": ["Person@example.com"], "subject": "Hello", "body": "Draft only"},
        }]
    })

    assert result[0]["status"] == "verified"
    assert result[0]["result"]["delivery"] == "not_sent"
    assert result[0]["postcondition"]["evidence"]["observed"] is True
    assert tools.run("email_list_drafts")["drafts"][0]["subject"] == "Hello"
    preview = tools.run("email_preview_draft", {"draft_id": result[0]["result"]["draft_id"]})
    assert preview["body"] == "Draft only"
    assert preview["delivery"] == "not_sent"


def test_email_today_count_is_honest_when_no_account_is_connected(tmp_path):
    tools = ToolRegistry()
    register_email_tools(tools, tmp_path)

    result = tools.run("email_count_today")

    assert result["ok"] is False
    assert result["status"] == "not_configured"
    assert "No mailbox was accessed" in result["message"]
    assert tools.run("email_search", {"query": "from:friend"})["status"] == "not_configured"
    assert tools.run("email_read_message", {"message_id": "message_1"})["status"] == "not_configured"


def test_email_search_and_read_route_only_to_configured_read_provider(tmp_path):
    class Provider:
        configured = True

        def search_messages(self, query, limit):
            return {"query": query, "limit": limit}

        def read_message(self, message_id):
            return {"message_id": message_id, "content_trust": "untrusted_email_content"}

    tools = ToolRegistry()
    register_email_tools(tools, tmp_path, provider=Provider())
    assert tools.run("email_search", {"query": "subject:invoice", "limit": 2}) == {
        "query": "subject:invoice", "limit": 2}
    assert tools.run("email_read_message", {"message_id": "m1"})["content_trust"] == "untrusted_email_content"


def test_email_today_count_uses_local_day_and_exposes_only_count(tmp_path):
    class Provider:
        source_name = "test mailbox"

        def count_received(self, start, end):
            assert start.tzinfo is not None and end.tzinfo is not None
            assert (end - start).total_seconds() == 24 * 60 * 60
            assert start.hour == 0 and start.minute == 0
            return 4

    tools = ToolRegistry()
    register_email_tools(tools, tmp_path, provider=Provider())
    now = datetime(2026, 10, 22, 14, 30, tzinfo=timezone.utc)

    result = tools.run("email_count_today", {"now": now})

    assert result == {
        "ok": True,
        "status": "observed",
        "count": 4,
        "start": "2026-10-22T00:00:00+00:00",
        "end_exclusive": "2026-10-23T00:00:00+00:00",
        "source": "test mailbox",
        "message_bodies_read": False,
    }


def test_email_today_count_rejects_untrusted_provider_counts(tmp_path):
    class Provider:
        def count_received(self, start, end):
            return True

    tools = ToolRegistry()
    register_email_tools(tools, tmp_path, provider=Provider())

    try:
        tools.run("email_count_today")
    except ValueError as exc:
        assert "invalid count" in str(exc)
    else:
        raise AssertionError("boolean provider count must be rejected")


def test_email_requests_are_routed_to_the_tool_planner():
    source = (Path(__file__).resolve().parents[2] / "alice" / "ui" / "app.py").read_text(encoding="utf-8")
    start = source.index("def _needs_tools(text):")
    end = source.index("def _wants_voice", start)
    routing = source[start:end]
    assert '"email"' in routing
