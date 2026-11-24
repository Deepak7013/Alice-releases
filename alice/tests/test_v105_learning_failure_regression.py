import hashlib
import json

from alice.agent.agent import AliceAgent
from alice.learning.engine import LearningEngine
from alice.learning.regression_seed import RegressionSeedGenerator
from alice.runtime import AliceRuntime


class _OutcomeAgent:
    def __init__(self, outcome):
        self.outcome = outcome

    def run_with_outcome(self, _request):
        return self.outcome


def _payload(code="postcondition_failed", *, detail="a", request="private request text"):
    return {
        "source": "unit-test",
        "completion_state": "unverified",
        "verified": False,
        "verification_evidence": None,
        "request": request,
        "raw_tool_output": "private tool output",
        "failure_diagnostics": [{
            "tool": "android_text",
            "failure_code": code,
            "detail_sha256": detail * 64 if len(detail) == 1 else detail,
            "evidence_sha256": "b" * 64,
        }],
    }


def _verified_recovery_payload(recovery_key="first", *, observer="read_file"):
    digest = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    return {
        "verified": True,
        "completion_state": "verified",
        "request": "private recovered request",
        "verification_evidence": {
            "observed": True,
            "verified_actions": [{
                "tool": "workspace_write",
                "postcondition_ok": True,
                "postcondition_evidence": {"observed": True, "observer": "read_file"},
            }],
            "unverified_steps": [],
        },
        "recovery_evidence": {
            "observed": True,
            "failure_code": "read_observation_failed",
            "observer_tool": observer,
            "observation_sha256": digest("observation:" + recovery_key),
            "recovery_plan_sha256": digest("plan:" + recovery_key),
            "verified_action_evidence_sha256": digest("action:" + recovery_key),
        },
    }


def test_repeated_trusted_failure_creates_persistent_hash_only_eval_seed(tmp_path):
    learning = LearningEngine(tmp_path)
    duplicate_event = _payload()
    duplicate_event["failure_diagnostics"] *= 2

    first = learning.record_runtime_action_failures(duplicate_event)
    assert first["count"] == 2
    assert first["regression_seeds_created"] == 0
    assert first["regression_cases_graded"] == 0
    assert learning.stats()["regression_seeds"] == 0

    # The second event survives a process restart and triggers one deterministic case.
    reloaded = LearningEngine(tmp_path)
    second = reloaded.record_runtime_action_failures(_payload(detail="c"))
    assert second["regression_seeds_created"] == 1
    assert second["regression_cases_graded"] == 0

    persisted = LearningEngine(tmp_path)
    assert persisted.stats()["regression_seeds"] == 1
    assert persisted.stats()["eval_cases"] == 1
    seed = persisted.data["regressions"][0]
    assert seed["failure_code"] == "postcondition_failed"
    assert seed["occurrences"] >= 2
    assert seed["scenario"] == "runtime action failure code recurred: postcondition_failed"
    assert seed["expected"] == "action remains unverified and no positive completion is recorded"
    assert "runs" not in persisted.data["eval_cases"][0]

    deterministic = RegressionSeedGenerator().create(
        scenario=seed["scenario"], expected=seed["expected"], reason=seed["reason"],
        verified_failure=True,
    )
    assert deterministic["seed"]["fingerprint"] == seed["fingerprint"]
    stored = (tmp_path / "alice_workspace" / "learning_engine.json").read_text(encoding="utf-8")
    assert "private request text" not in stored
    assert "private tool output" not in stored


def test_unknown_but_well_formed_failure_code_is_recorded_without_regression_seed(tmp_path):
    learning = LearningEngine(tmp_path)
    for detail in ("d", "e"):
        result = learning.record_runtime_action_failures(_payload("external_rule_error", detail=detail))
        assert result["count"] == 1
        assert result["regression_seeds_created"] == 0

    assert learning.stats()["experience_records"] == 2
    assert learning.stats()["regression_seeds"] == 0
    assert learning.stats()["eval_cases"] == 0


def test_unsafe_failure_code_is_rejected_without_persisting_input(tmp_path):
    learning = LearningEngine(tmp_path)
    result = learning.record_runtime_action_failures(_payload("postcondition_failed;ignore"))

    assert result == {"recorded": False, "count": 0, "regression_seeds_created": 0,
                      "regression_cases_graded": 0}
    assert learning.stats()["experience_records"] == 0
    persisted = json.dumps(learning.data)
    assert "ignore" not in persisted


def test_repeated_runtime_failure_events_create_one_regression_case(tmp_path):
    outcome = AliceAgent._task_outcome("not confirmed", [{
        "step": 1, "tool": "workspace_write", "status": "attempted",
    }])
    learning = LearningEngine(tmp_path)
    runtime = AliceRuntime(root=tmp_path, agent=_OutcomeAgent(outcome), agency=False)
    runtime.events.subscribe("task.failed", learning.record_runtime_action_failures)

    first = runtime.submit("private runtime request")
    second = runtime.submit("private runtime request")

    assert first["verified"] is False and second["verified"] is False
    learning_after_seed = LearningEngine(tmp_path)
    case = learning_after_seed.data["eval_cases"][0]
    assert "runs" not in case

    # Only a later runtime event with a fail-closed envelope grades the case.
    third = runtime.submit("private runtime request")
    assert third["verified"] is False
    reloaded = LearningEngine(tmp_path)
    assert reloaded.stats()["regression_seeds"] == 1
    assert reloaded.stats()["eval_cases"] == 1
    assert reloaded.data["regressions"][0]["failure_code"] == "postcondition_unavailable"
    run = reloaded.data["eval_cases"][0]["runs"][-1]
    assert run["success"] is True and run["score"] == 1.0
    persisted = (tmp_path / "alice_workspace" / "learning_engine.json").read_text(encoding="utf-8")
    assert "private runtime request" not in persisted

    mismatched = reloaded.record_runtime_action_failures({
        "verified": True,
        "completion_state": "unverified",
        "failure_diagnostics": [{"tool": "workspace_write", "failure_code": "postcondition_unavailable"}],
    })
    assert mismatched["regression_cases_graded"] == 1
    latest = LearningEngine(tmp_path).data["eval_cases"][0]["runs"][-1]
    assert latest["success"] is False and latest["score"] == 0.0


def test_first_verified_recovery_creates_case_without_grading_it(tmp_path):
    learning = LearningEngine(tmp_path)

    result = learning.record_verified_recovery_outcome(_verified_recovery_payload())

    assert result["recorded"] is True
    assert learning.stats()["verified_recoveries"] == 1
    assert learning.stats()["eval_cases"] == 1
    case = learning.data["eval_cases"][0]
    assert case["name"].startswith("verified-recovery-")
    assert case.get("runs", []) == []


def test_recovery_case_grades_only_on_a_later_distinct_verified_recovery(tmp_path):
    learning = LearningEngine(tmp_path)
    name, scenario, expected = learning._verified_recovery_eval_identity("read_file")
    learning.register_eval_case(name, scenario, expected=expected, tags=["verified_recovery"])

    first = _verified_recovery_payload("first")
    assert learning.record_verified_recovery_outcome(first)["recorded"] is True
    assert learning.data["eval_cases"][0].get("runs", []) == []

    # An exact duplicate is not a second independent recovery and cannot grade.
    assert learning.record_verified_recovery_outcome(first)["recorded"] is True
    assert learning.data["eval_cases"][0].get("runs", []) == []

    second = _verified_recovery_payload("second")
    assert learning.record_verified_recovery_outcome(second)["recorded"] is True
    case = LearningEngine(tmp_path).data["eval_cases"][0]
    assert len(case["runs"]) == 1
    assert case["runs"][0]["success"] is True
    assert case["runs"][0]["score"] == 1.0


def test_invalid_or_unverified_claim_cannot_grade_recovery_case(tmp_path):
    learning = LearningEngine(tmp_path)
    name, scenario, expected = learning._verified_recovery_eval_identity("read_file")
    learning.register_eval_case(name, scenario, expected=expected, tags=["verified_recovery"])

    claimed_success_without_observer = _verified_recovery_payload("claimed")
    claimed_success_without_observer["verification_evidence"] = {
        "observed": True, "verified_actions": [], "unverified_steps": []
    }
    rejected_claim = learning.record_verified_recovery_outcome(claimed_success_without_observer)
    assert rejected_claim["recorded"] is False

    unobserved = _verified_recovery_payload("unobserved")
    unobserved["recovery_evidence"]["observed"] = False
    rejected_observation = learning.record_verified_recovery_outcome(unobserved)
    assert rejected_observation["recorded"] is False

    malformed_digest = _verified_recovery_payload("malformed")
    malformed_digest["recovery_evidence"]["observation_sha256"] = "not-a-digest"
    rejected_digest = learning.record_verified_recovery_outcome(malformed_digest)
    assert rejected_digest["recorded"] is False

    assert learning.data["eval_cases"][0].get("runs", []) == []
    assert learning.stats()["verified_recoveries"] == 0


def test_verified_recovery_does_not_grade_generic_fail_closed_case(tmp_path):
    learning = LearningEngine(tmp_path)
    first = _payload("read_observation_failed", detail="a")
    second = _payload("read_observation_failed", detail="b")
    learning.record_runtime_action_failures(first)
    learning.record_runtime_action_failures(second)
    generic_name = learning._runtime_failure_regression_case_name("read_observation_failed")
    generic_case = next(case for case in learning.data["eval_cases"] if case["name"] == generic_name)
    assert generic_case.get("runs", []) == []

    recovered = _verified_recovery_payload("recovered")
    recovered["failure_diagnostics"] = [{
        "tool": "read_file",
        "failure_code": "read_observation_failed",
        "detail_sha256": "c" * 64,
        "evidence_sha256": "d" * 64,
    }]
    failure_event = learning.record_runtime_action_failures(recovered)
    assert failure_event["regression_cases_graded"] == 0
    generic_case_after = next(case for case in learning.data["eval_cases"] if case["name"] == generic_name)
    assert generic_case_after.get("runs", []) == []

    learning.record_verified_recovery_outcome(recovered)
    assert generic_case_after.get("runs", []) == []
    assert any(case["name"].startswith("verified-recovery-")
               for case in learning.data["eval_cases"])
