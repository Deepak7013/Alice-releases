"""Regression tests for untrusted planner output at the executor boundary."""
from alice.agent.executor import Executor
from alice.tools.registry import ToolRegistry


def _executor(calls):
    registry = ToolRegistry()
    registry.add("record", "record an invocation", lambda value="ok": calls.append(value) or {"ok": True})
    executor = Executor(registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    return executor


def test_non_object_plan_is_reported_without_exception_or_side_effect():
    calls = []
    result = _executor(calls).run([{"tool": "record"}])
    assert result[0]["error_class"] == "PlanValidationError"
    assert calls == []


def test_missing_or_non_list_steps_are_reported():
    executor = _executor([])
    assert "steps must be a list" in executor.run({})[0]["error"]
    assert "steps must be a list" in executor.run({"steps": {}})[0]["error"]


def test_malformed_steps_do_not_crash_or_invoke_tools():
    calls = []
    result = _executor(calls).run({"steps": [None, {}, {"tool": "record", "args": []}]})
    assert len(result) == 1  # fail closed at the first malformed step
    assert result[0]["error_class"] == "PlanValidationError"
    assert calls == []


def test_valid_step_still_executes_after_structural_validation():
    calls = []
    result = _executor(calls).run({"steps": [{"tool": "record", "args": {"value": "ok"}}]})
    assert result[0]["status"] == "observed"
    assert calls == ["ok"]


def test_denied_step_stops_later_plan_steps():
    calls = []
    registry = ToolRegistry()
    registry.add("first", "first", lambda: {"status": "denied"}, "read")
    registry.add("second", "second", lambda: calls.append("second") or {"ok": True}, "read")
    executor = Executor(registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "first"}, {"tool": "second"}]})

    assert len(result) == 1
    assert result[0]["status"] == "denied"
    assert calls == []


def test_tool_exception_stops_later_plan_steps():
    calls = []
    registry = ToolRegistry()

    def fail():
        raise RuntimeError("simulated failure")

    registry.add("first", "first", fail, "read")
    registry.add("second", "second", lambda: calls.append("second") or {"ok": True}, "read")
    executor = Executor(registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "first"}, {"tool": "second"}]})

    assert len(result) == 1
    assert result[0]["status"] == "error"
    assert result[0]["effect_may_have_occurred"] is False
    assert calls == []


def test_unknown_tool_stops_later_plan_steps():
    calls = []
    registry = ToolRegistry()
    registry.add("second", "second", lambda: calls.append("second") or {"ok": True}, "read")
    executor = Executor(registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "missing"}, {"tool": "second"}]})

    assert len(result) == 1
    assert result[0]["error_class"] == "UnknownToolError"
    assert calls == []
