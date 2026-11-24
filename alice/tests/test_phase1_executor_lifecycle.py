"""Cooperative cancellation and deadline checks at safe execution boundaries."""
from threading import Event
from alice.agent.executor import Executor
from alice.tools.registry import ToolRegistry


def make_executor(calls):
    registry = ToolRegistry()
    registry.add("record", "record invocation", lambda value="ok": calls.append(value) or {"ok": True})
    executor = Executor(registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    return executor


def test_cancelled_before_start_does_not_invoke_tool():
    calls = []
    event = Event(); event.set()
    result = make_executor(calls).run({"steps": [{"tool": "record"}]}, cancel_event=event)
    assert result[0]["status"] == "cancelled"
    assert result[0]["effect_may_have_occurred"] is False
    assert calls == []


def test_cancellation_between_steps_prevents_next_tool():
    calls = []
    registry = ToolRegistry()
    event = Event()
    def first():
        calls.append("first")
        event.set()
        return {"ok": True}
    registry.add("first", "first", first, "read")
    registry.add("second", "second", lambda: calls.append("second") or {"ok": True}, "read")
    executor = Executor(registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    result = executor.run({"steps": [{"tool": "first"}, {"tool": "second"}]}, cancel_event=event)
    assert [x["status"] for x in result] == ["observed", "cancelled"]
    assert calls == ["first"]


def test_expired_deadline_prevents_tool_start():
    calls = []
    result = make_executor(calls).run({"steps": [{"tool": "record"}]}, timeout_seconds=1e-12)
    assert result[0]["status"] == "timed_out"
    assert result[0]["effect_may_have_occurred"] is False
    assert calls == []


def test_invalid_deadline_is_rejected():
    executor = make_executor([])
    for value in (0, -1, float("inf"), float("nan"), "bad"):
        try:
            executor.run({"steps": []}, timeout_seconds=value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid timeout: {value!r}")


def test_legacy_run_without_lifecycle_options_still_works():
    calls = []
    result = make_executor(calls).run({"steps": [{"tool": "record"}]})
    assert result[0]["status"] == "observed"
    assert calls == ["ok"]
    assert result[0]["execution_elapsed_seconds"] >= 0


def test_cancellation_during_approval_prevents_tool_invocation():
    calls = []
    event = Event()
    executor = make_executor(calls)
    executor.permissions.needs_confirmation = lambda _name, _args: True
    def approve(_title, _details):
        event.set()
        return True
    executor.permissions.request = approve
    result = executor.run({"steps": [{"tool": "record"}]}, cancel_event=event)
    assert result[0]["status"] == "cancelled"
    assert result[0]["effect_may_have_occurred"] is False
    assert calls == []


def test_deadline_expiring_during_approval_prevents_tool_invocation(monkeypatch):
    calls = []
    executor = make_executor(calls)
    executor.permissions.needs_confirmation = lambda _name, _args: True
    clock = iter((100.0, 100.0, 102.0, 102.0))
    monkeypatch.setattr("alice.agent.executor.time.monotonic", lambda: next(clock))
    executor.permissions.request = lambda _title, _details: True
    result = executor.run({"steps": [{"tool": "record"}]}, timeout_seconds=1.0)
    assert result[0]["status"] == "timed_out"
    assert result[0]["effect_may_have_occurred"] is False
    assert calls == []


def test_boolean_execution_budget_is_rejected():
    executor = make_executor([])
    for value in (True, False):
        try:
            executor.run({"steps": []}, timeout_seconds=value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted boolean timeout: {value!r}")
