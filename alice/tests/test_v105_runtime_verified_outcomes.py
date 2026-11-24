from alice.agent.agent import AliceAgent
from alice.learning.engine import LearningEngine
from alice.runtime import AliceRuntime
from alice.runtime.outcomes import has_verified_action_evidence, is_verified_action_outcome


class OutcomeAgent:
    def __init__(self, outcome):
        self.outcome = outcome

    def run_with_outcome(self, _request):
        return self.outcome


def _verified_results():
    return [{
        "step": 1,
        "tool": "write_file",
        "status": "verified",
        "postcondition": {
            "ok": True,
            "evidence": {"observed": True, "path": "workspace/result.txt", "content_matches": True},
        },
    }]


def test_agent_task_outcome_requires_observed_postcondition_evidence():
    verified = AliceAgent._task_outcome("saved", _verified_results())
    attempted = AliceAgent._task_outcome(
        "File was saved successfully.",
        [{"step": 1, "tool": "write_file", "status": "attempted"}],
    )

    assert verified["verified"] is True
    assert verified["completion_state"] == "verified"
    assert is_verified_action_outcome(verified)
    assert attempted["verified"] is False
    assert attempted["completion_state"] == "unverified"
    assert "successfully" not in attempted["summary"].lower()
    assert "can't report it as done" in attempted["summary"]
    assert not is_verified_action_outcome(attempted)


def test_mixed_results_keep_verified_action_but_withhold_overall_success_claim():
    outcome = AliceAgent._task_outcome(
        "Everything completed successfully.",
        _verified_results() + [{"step": 2, "tool": "send_message", "status": "attempted"}],
    )

    assert outcome["completion_state"] == "unverified"
    assert "Verified: write_file." in outcome["summary"]
    assert "send_message (attempted)" in outcome["summary"]
    assert "successfully" not in outcome["summary"].lower()


def test_runtime_publishes_positive_completion_only_for_observed_mutation(tmp_path):
    outcome = AliceAgent._task_outcome("saved", _verified_results())
    runtime = AliceRuntime(root=tmp_path, agent=OutcomeAgent(outcome), agency=False)
    completed = []
    failed = []
    runtime.events.subscribe("task.completed", completed.append)
    runtime.events.subscribe("task.failed", failed.append)

    result = runtime.submit("save the result")

    assert result["status"] == "completed"
    assert result["verified"] is True
    assert len(completed) == 1
    assert completed[0]["verification_evidence"]["verified_actions"][0]["tool"] == "write_file"
    assert not failed


def test_runtime_treats_attempted_side_effect_as_unverified_failure(tmp_path):
    outcome = AliceAgent._task_outcome("sent, but not observed", [
        {"step": 1, "tool": "send_message", "status": "attempted"},
    ])
    runtime = AliceRuntime(root=tmp_path, agent=OutcomeAgent(outcome), agency=False)
    completed = []
    failed = []
    runtime.events.subscribe("task.completed", completed.append)
    runtime.events.subscribe("task.failed", failed.append)

    result = runtime.submit("send the message")

    assert result["verified"] is False
    assert result["completion_state"] == "unverified"
    assert not completed
    assert len(failed) == 1
    assert failed[0]["error"] == "action_outcome_unverified"


def test_runtime_rejects_claimed_verified_state_without_a_real_observer(tmp_path):
    outcome = {
        "summary": "done",
        "verified": True,
        "completion_state": "verified",
        "verification_evidence": {
            "observed": True,
            "verified_actions": [{
                "tool": "send_message",
                "postcondition_ok": True,
                "postcondition_evidence": {"observed": False},
            }],
            "unverified_steps": [],
        },
    }
    runtime = AliceRuntime(root=tmp_path, agent=OutcomeAgent(outcome), agency=False)
    completed = []
    failed = []
    runtime.events.subscribe("task.completed", completed.append)
    runtime.events.subscribe("task.failed", failed.append)

    result = runtime.submit("send the message")

    assert result["verified"] is False
    assert result["completion_state"] == "unverified"
    assert not completed
    assert len(failed) == 1


def test_verified_evidence_validator_rejects_empty_or_mixed_actions():
    assert not has_verified_action_evidence({"observed": True, "verified_actions": [], "unverified_steps": []})
    mixed = AliceAgent._task_outcome("partial", _verified_results() + [
        {"step": 2, "tool": "send_message", "status": "attempted"},
    ])
    assert mixed["verified"] is False
    assert not is_verified_action_outcome(mixed)


def test_learning_persists_only_verified_runtime_outcomes(tmp_path):
    learning = LearningEngine(tmp_path)
    unverified = learning.record_verified_runtime_outcome({
        "request": "send a message", "verified": False,
        "verification_evidence": {"observed": False, "verified_actions": []},
    })
    assert unverified["recorded"] is False
    assert LearningEngine(tmp_path).stats()["experience_records"] == 0

    outcome = AliceAgent._task_outcome("message visible", _verified_results())
    runtime = AliceRuntime(root=tmp_path, agent=OutcomeAgent(outcome), agency=False)
    runtime.events.subscribe("task.completed", learning.record_verified_runtime_outcome)
    result = runtime.submit("write a result", source="test")
    reloaded = LearningEngine(tmp_path)
    assert result["verified"] is True
    assert reloaded.stats()["experience_records"] == 1
    assert reloaded.store.records[-1].success is True
    assert reloaded.data["lessons"][0]["attempts"] == 1


def test_unverified_action_failure_persists_hash_only_diagnostic(tmp_path):
    private_detail = "private typed message body"
    outcome = AliceAgent._task_outcome("not confirmed", [{
        "step": 1,
        "tool": "android_text",
        "status": "failed_verification",
        "postcondition": {
            "ok": False,
            "reason": private_detail,
            "evidence": {"observed": False, "text": private_detail},
        },
    }])
    assert outcome["failure_diagnostics"][0]["failure_code"] == "postcondition_failed"
    assert private_detail not in repr(outcome["failure_diagnostics"])

    learning = LearningEngine(tmp_path)
    runtime = AliceRuntime(root=tmp_path, agent=OutcomeAgent(outcome), agency=False)
    failed = []
    runtime.events.subscribe("task.failed", failed.append)
    runtime.events.subscribe("task.failed", learning.record_runtime_action_failures)

    result = runtime.submit("type the private message")

    assert result["completion_state"] == "unverified"
    assert failed and failed[0]["failure_diagnostics"][0]["tool"] == "android_text"
    assert LearningEngine(tmp_path).stats()["experience_records"] == 1
    persisted = (tmp_path / "alice_workspace" / "global_experience.json").read_text(encoding="utf-8")
    assert private_detail not in persisted
    assert "type the private message" not in persisted
    assert "detail_sha256" in persisted and "evidence_sha256" in persisted
