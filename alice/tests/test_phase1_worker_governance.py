import json

from alice.agents.worker import SpecialistWorker, WorkerSpec
from alice.tools.registry import ToolRegistry


class FakeRouter:
    def __init__(self, plan):
        self.plan = plan

    def ask(self, prompt):
        return json.dumps(self.plan)


def test_specialist_worker_routes_registered_tools_through_executor(monkeypatch):
    calls = []
    tools = ToolRegistry()
    tools.add("read_status", "Read status", lambda: calls.append("called") or {"ok": True}, "read")
    worker = SpecialistWorker(
        FakeRouter({"summary": "Read completed", "steps": [{"tool": "read_status", "args": {}}]}),
        tools,
        WorkerSpec(name="reader", role="reader", objective="Read status", allowed_tools=["read_status"]),
    )

    result = worker.run()

    assert result.status == "completed"
    assert calls == ["called"]
    assert result.tool_results[0]["result"]["status"] == "observed"


def test_specialist_worker_rejects_unknown_or_unlisted_tools_before_execution():
    calls = []
    tools = ToolRegistry()
    tools.add("safe_read", "Safe read", lambda: calls.append("called"), "read")
    worker = SpecialistWorker(
        FakeRouter({"steps": [{"tool": "not_allowed", "args": {}}]}),
        tools,
        WorkerSpec(name="reader", role="reader", objective="Read", allowed_tools=["safe_read"]),
    )

    result = worker.run()

    assert result.status == "failed"
    assert "not allowed" in result.error.lower()
    assert calls == []


def test_worker_rejects_invalid_execution_budgets():
    tools = ToolRegistry()
    try:
        SpecialistWorker(FakeRouter({"steps": []}), tools,
                         WorkerSpec(name="bad", role="x", objective="x", max_steps=0))
    except ValueError as exc:
        assert "max_steps" in str(exc)
    else:
        raise AssertionError("zero-step worker budget should be rejected")


def test_specialist_worker_cannot_bypass_confirmation_for_write_tools():
    calls = []
    tools = ToolRegistry()
    tools.add("run_windows_command", "Run Windows command", lambda value: calls.append(value) or {"ok": True}, "write")
    worker = SpecialistWorker(
        FakeRouter({"steps": [{"tool": "run_windows_command", "args": {"value": "x"}}]}),
        tools,
        WorkerSpec(name="writer", role="writer", objective="Write", allowed_tools=["run_windows_command"], risk="write"),
    )
    worker.executor.permissions.request = lambda *_args, **_kwargs: False

    result = worker.run()

    assert result.status == "failed"
    assert calls == []
    assert result.tool_results[0]["result"]["status"] == "denied"
