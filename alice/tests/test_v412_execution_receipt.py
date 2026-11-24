import pytest
from alice.execution.execution_receipt import ExecutionReceiptFactory


def test_creates_conservative_receipt():
    r = ExecutionReceiptFactory().create(
        action_id="a1", tool="desktop", admitted=True,
        execution_ok=True, verified=True, outcome="verified", evidence="screen=ready"
    )
    assert r.verified and r.execution_ok and r.admitted


def test_missing_action_id_rejected():
    with pytest.raises(ValueError, match="action_id_required"):
        ExecutionReceiptFactory().create(
            action_id="", tool="desktop", admitted=True,
            execution_ok=True, verified=True, outcome="verified"
        )


def test_missing_tool_rejected():
    with pytest.raises(ValueError, match="tool_required"):
        ExecutionReceiptFactory().create(
            action_id="a1", tool="", admitted=True,
            execution_ok=True, verified=True, outcome="verified"
        )


def test_verified_cannot_follow_failed_execution():
    with pytest.raises(ValueError, match="verified_requires_execution_success"):
        ExecutionReceiptFactory().create(
            action_id="a1", tool="desktop", admitted=True,
            execution_ok=False, verified=True, outcome="verified"
        )


def test_execution_success_requires_admission():
    with pytest.raises(ValueError, match="execution_success_requires_admission"):
        ExecutionReceiptFactory().create(
            action_id="a1", tool="desktop", admitted=False,
            execution_ok=True, verified=False, outcome="ran"
        )


def test_failed_execution_can_be_recorded_without_claiming_success():
    r = ExecutionReceiptFactory().create(
        action_id="a1", tool="desktop", admitted=True,
        execution_ok=False, verified=False, outcome="failed", evidence="timeout"
    )
    assert not r.execution_ok and not r.verified and r.outcome == "failed"


@pytest.mark.parametrize("field,value", [
    ("admitted", "false"),
    ("execution_ok", 1),
    ("verified", None),
])
def test_receipt_factory_rejects_boolean_coercion(field, value):
    values = dict(action_id="a1", tool="desktop", admitted=True,
                  execution_ok=False, verified=False, outcome="failed")
    values[field] = value
    with pytest.raises(ValueError, match="receipt_flags_must_be_boolean"):
        ExecutionReceiptFactory().create(**values)


@pytest.mark.parametrize("field,value,error", [
    ("action_id", 42, "action_id_required"),
    ("tool", None, "tool_required"),
    ("outcome", False, "outcome_required"),
    ("evidence", object(), "evidence_must_be_string"),
    ("action_id", "x" * 513, "action_id_too_long"),
    ("tool", "x" * 513, "tool_too_long"),
    ("outcome", "x" * 129, "outcome_too_long"),
    ("evidence", "x" * 4097, "evidence_too_long"),
])
def test_receipt_factory_rejects_invalid_or_unbounded_fields(field, value, error):
    values = dict(action_id="a1", tool="desktop", admitted=True,
                  execution_ok=False, verified=False, outcome="failed", evidence="")
    values[field] = value
    with pytest.raises(ValueError, match=error):
        ExecutionReceiptFactory().create(**values)
