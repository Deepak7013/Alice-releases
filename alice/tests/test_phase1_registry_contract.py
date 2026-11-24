import pytest

from alice.tools.registry import ToolArgumentError, ToolRegistry


def test_registry_exposes_signature_contract_and_safety_metadata():
    registry = ToolRegistry()

    def create_folder(path: str, parents: bool = False):
        return {"created": path, "parents": parents}

    tool = registry.add(
        "create_folder", "Create a folder", create_folder, "write",
        timeout_seconds=12, preconditions=("target_path_allowed",),
        verification="folder_exists_after_call",
    )

    assert tool.input_schema["required"] == ["path"]
    assert tool.input_schema["properties"]["parents"]["default"] is False
    assert tool.timeout_seconds == 12
    assert tool.preconditions == ("target_path_allowed",)
    assert registry.inventory()[0]["verification"] == "folder_exists_after_call"


def test_registry_rejects_invalid_contract_before_side_effect():
    calls = []
    registry = ToolRegistry()
    registry.add("mutate", "Mutate", lambda target: calls.append(target), "write")

    with pytest.raises(ToolArgumentError, match="Invalid arguments"):
        registry.run("mutate", {"unexpected": "value"})
    with pytest.raises(ToolArgumentError, match="missing a required argument"):
        registry.run("mutate", {})

    assert calls == []


def test_registry_rejects_invalid_registration_metadata():
    registry = ToolRegistry()
    with pytest.raises(TypeError, match="callable"):
        registry.add("not_callable", "Bad", None)
    with pytest.raises(ValueError, match="risk classification"):
        registry.add("bad_risk", "Bad", lambda: None, "dangerous")
    with pytest.raises(ValueError, match="positive finite"):
        registry.add("bad_timeout", "Bad", lambda: None, timeout_seconds=0)


def test_registry_preserves_kwargs_tools_and_callable_snapshot_guard():
    registry = ToolRegistry()
    registry.add("flexible", "Flexible", lambda **kwargs: kwargs)
    assert registry.run("flexible", {"x": 1}) == {"x": 1}
    old = registry.get("flexible")
    registry.add("flexible", "Replaced", lambda: "new")
    with pytest.raises(ValueError, match="changed before execution"):
        registry.run_registered(old, {})



def test_explicit_schema_rejects_wrong_types_and_ranges_before_side_effect():
    calls = []
    registry = ToolRegistry()
    registry.add(
        "set_volume", "Set volume", lambda level: calls.append(level), "write",
        input_schema={
            "type": "object",
            "properties": {"level": {"type": "integer", "minimum": 0, "maximum": 100}},
            "required": ["level"],
            "additionalProperties": False,
        },
    )

    with pytest.raises(ToolArgumentError, match="type integer"):
        registry.run("set_volume", {"level": "loud"})
    with pytest.raises(ToolArgumentError, match="at most 100"):
        registry.run("set_volume", {"level": 101})
    with pytest.raises(ToolArgumentError, match="unexpected property"):
        registry.run("set_volume", {"level": 50, "admin": True})
    assert calls == []


def test_explicit_schema_accepts_valid_arguments_and_nested_arrays():
    registry = ToolRegistry()
    registry.add(
        "batch", "Batch operation", lambda items: {"count": len(items)}, "read",
        input_schema={
            "type": "object",
            "properties": {
                "items": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}}
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    )
    assert registry.run("batch", {"items": ["one", "two"]}) == {"count": 2}
    with pytest.raises(ToolArgumentError, match=r"items\[0\]"):
        registry.run("batch", {"items": [""]})


def test_explicit_schema_rejects_unsupported_keywords_at_registration():
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="Unsupported input schema keywords"):
        registry.add(
            "regex_tool", "Bad schema", lambda value: value, "read",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "string", "pattern": ".*"}},
            },
        )


@pytest.mark.parametrize("schema, message", [
    ({"type": "object", "properties": {}, "required": ["missing"]}, "undefined properties"),
    ({"type": "object", "properties": {}, "required": ["x", "x"]}, "unique strings"),
    ({"type": "object", "properties": {"x": {"type": "string", "minLength": -1}}}, "non-negative integer"),
    ({"type": "object", "properties": {"x": {"type": "number", "minimum": 5, "maximum": 2}}}, "cannot exceed maximum"),
    ({"type": "object", "properties": {"x": {"type": "string", "items": {"type": "string"}}}}, "requires type=array"),
    ({"type": "object", "properties": {"x": {"type": "string", "enum": []}}}, "non-empty list"),
])
def test_explicit_schema_definition_is_rejected_when_internally_inconsistent(schema, message):
    registry = ToolRegistry()
    with pytest.raises(ValueError, match=message):
        registry.add("invalid_schema", "Invalid", lambda **kwargs: kwargs, input_schema=schema)


def test_registered_schema_cannot_be_weakened_through_returned_metadata():
    calls = []
    registry = ToolRegistry()
    tool = registry.add(
        "guarded", "Guarded write", lambda value: calls.append(value), "write",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "integer", "minimum": 1}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )

    # Mutate every public view that used to expose nested schema dictionaries.
    tool.input_schema["properties"]["value"]["minimum"] = -100
    described = registry.describe()
    described["guarded"]["input_schema"]["properties"]["value"]["minimum"] = -200
    inventory = registry.inventory()
    inventory[0]["input_schema"]["properties"]["value"]["minimum"] = -300

    with pytest.raises(ToolArgumentError, match="at least 1"):
        registry.run("guarded", {"value": 0})
    assert calls == []


def test_registry_rejects_boolean_timeout_metadata():
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="positive finite"):
        registry.add("boolean_timeout", "Bad", lambda: None, timeout_seconds=True)


def test_output_schema_is_enforced_after_callable_returns():
    from alice.tools.registry import ToolOutputError

    calls = []
    registry = ToolRegistry()
    registry.add(
        "read_status", "Read status", lambda: calls.append("called") or {"ready": "yes"},
        output_schema={"type": "object", "properties": {"ready": {"type": "boolean"}},
                      "required": ["ready"], "additionalProperties": False},
    )

    with pytest.raises(ToolOutputError, match="returned an invalid result"):
        registry.run("read_status")
    assert calls == ["called"]  # Output validation cannot undo a completed call.


def test_output_schema_accepts_valid_result_and_rejects_bad_schema():
    registry = ToolRegistry()
    registry.add("status", "Status", lambda: {"ready": True},
                 output_schema={"type": "object", "properties": {"ready": {"type": "boolean"}},
                                "required": ["ready"], "additionalProperties": False})
    assert registry.run("status") == {"ready": True}

    with pytest.raises(ValueError, match="output_schema"):
        registry.add("bad_output", "Bad", lambda: None, output_schema={"type": "object", "pattern": "x"})


def test_cooperative_cancellation_requires_explicit_keyword_parameter():
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="cancel_event"):
        registry.add("bad_cancel", "bad", lambda: None, cancellation_supported=True)


def test_cancellation_metadata_must_be_boolean():
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="must be a boolean"):
        registry.add("bad_cancel_type", "bad", lambda: None, cancellation_supported="yes")


def test_cooperative_cancellation_token_is_forwarded_by_executor():
    from threading import Event
    from alice.agent.executor import Executor

    received = []
    registry = ToolRegistry()
    registry.add(
        "cooperative", "cooperative test tool",
        lambda cancel_event=None: received.append(cancel_event) or {"ok": True},
        risk="read", cancellation_supported=True,
    )
    executor = Executor(registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    event = Event()
    result = executor.run({"steps": [{"tool": "cooperative"}]}, cancel_event=event)
    assert len(received) == 1
    assert received[0].is_set() is False
    assert result[0]["cancellation_mode"] == "cooperative_token"
    assert result[0]["timeout_enforcement"] == "cooperative_signal_only"


def test_registry_inventory_does_not_overstate_timeout_enforcement():
    registry = ToolRegistry()
    registry.add("ordinary", "ordinary", lambda: None, timeout_seconds=4)
    description = registry.describe()["ordinary"]
    inventory = registry.inventory()[0]
    assert description["timeout_seconds"] == 4
    assert description["timeout_enforcement"] == "not_enforced_for_in_process_callable"
    assert inventory["timeout_enforcement"] == "not_enforced_for_in_process_callable"


def test_cooperative_tool_receives_timeout_signal_and_reports_timeout():
    import time
    import pytest
    from alice.tools.registry import ToolTimeoutError

    observed = []
    registry = ToolRegistry()

    def cooperative(cancel_event):
        deadline = time.monotonic() + 1
        while not cancel_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.002)
        observed.append(cancel_event.is_set())
        return {"stopped": cancel_event.is_set()}

    tool = registry.add("cooperative_timeout", "cooperative timeout", cooperative,
                        cancellation_supported=True, timeout_seconds=0.03)
    with pytest.raises(ToolTimeoutError):
        registry.run_registered(tool, {})
    assert observed == [True]


def test_cooperative_timeout_uses_shorter_plan_budget():
    import time
    import pytest
    from alice.agent.executor import Executor
    from alice.tools.registry import ToolTimeoutError

    observed = []
    registry = ToolRegistry()

    def cooperative(cancel_event):
        start = time.monotonic()
        while not cancel_event.is_set():
            time.sleep(0.002)
        observed.append(time.monotonic() - start)
        return {"stopped": True}

    registry.add("cooperative_budget", "cooperative budget", cooperative,
                 cancellation_supported=True, timeout_seconds=2)
    executor = Executor(registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    result = executor.run({"steps": [{"tool": "cooperative_budget"}]}, timeout_seconds=0.04)
    assert result[0]["status"] == "error"
    assert result[0]["error_class"] == "ToolTimeoutError"
    assert result[0]["effect_may_have_occurred"] is False
    assert observed and observed[0] < 0.5


def test_noncooperative_tool_timeout_remains_explicitly_unenforced():
    registry = ToolRegistry()
    registry.add("ordinary_timeout", "ordinary timeout", lambda: "ok", timeout_seconds=0.01)
    assert registry.describe()["ordinary_timeout"]["timeout_enforcement"] == "not_enforced_for_in_process_callable"
