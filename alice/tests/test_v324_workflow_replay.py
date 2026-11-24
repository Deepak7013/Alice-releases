import json

from alice.experience.replay import WorkflowReplay


def _read_result(tool="read_file", step=1):
    return {"step": step, "tool": tool, "status": "observed", "verified": False}


def _verified_result(tool="write_file", step=1, evidence=None):
    return {
        "step": step,
        "tool": tool,
        "status": "verified",
        "verified": True,
        "postcondition": {
            "ok": True,
            "evidence": evidence or {"observed": True, "content_matches": True},
        },
    }


def test_exact_observed_read_only_workflow_is_recalled(tmp_path):
    replay = WorkflowReplay(tmp_path)
    plan = {"steps": [{"tool": "read_file", "args": {"path": "x.txt"}, "risk": "read"}]}

    assert replay.record("read x.txt", plan, [_read_result()])
    candidate = replay.candidate("read x.txt")
    assert candidate and candidate["verified"] and candidate["replay_safe"]
    assert candidate["steps"][0]["tool"] == "read_file"
    assert candidate["steps"][0]["argument_keys"] == ["path"]


def test_verified_mutation_is_advisory_and_persisted_args_are_private(tmp_path):
    replay = WorkflowReplay(tmp_path)
    private_request = "write my private message: Alice account 8842"
    private_text = "message body that must not be persisted"
    plan = {"steps": [{"tool": "write_file", "args": {"path": "C:/private.txt", "text": private_text}, "risk": "write"}]}

    assert replay.record(private_request, plan, [_verified_result()])
    candidate = replay.candidate(private_request)
    assert candidate and candidate["verified"] and not candidate["replay_safe"]
    stored = replay.path.read_text(encoding="utf-8")
    assert private_request not in stored
    assert private_text not in stored
    assert "C:/private.txt" not in stored
    assert "args\"" not in stored
    assert json.loads(stored)["workflows"][0]["verification_version"] == replay.VERSION


def test_legacy_claimed_ok_does_not_become_verified_replay(tmp_path):
    replay = WorkflowReplay(tmp_path)
    plan = {"steps": [{"tool": "read_file", "args": {"path": "x.txt"}}]}

    assert not replay.record("read x", plan, [{"step": 1, "tool": "read_file", "status": "ok"}])
    assert replay.candidate("read x") is None


def test_replay_rejects_unverified_mutation_failed_postcondition_and_tool_mismatch(tmp_path):
    replay = WorkflowReplay(tmp_path)
    plan = {"steps": [{"tool": "write_file", "args": {"text": "private"}}]}

    attempted = {"step": 1, "tool": "write_file", "status": "attempted", "verified": False}
    failed_check = _verified_result(evidence={"observed": False})
    mismatch = _verified_result(tool="other_tool")
    assert not replay.record("attempt", plan, [attempted])
    assert not replay.record("failed check", plan, [failed_check])
    assert not replay.record("mismatch", plan, [mismatch])
    assert not replay.record("missing result", plan, [])
    assert replay.stats()["workflows"] == 0


def test_legacy_persisted_workflow_is_not_recalled(tmp_path):
    replay = WorkflowReplay(tmp_path)
    replay.path.write_text(json.dumps({"workflows": [{
        "signature": "legacy", "verified": True,
        "request": "sensitive old request",
        "steps": [{"tool": "click", "args": {"x": 1}}],
    }]}), encoding="utf-8")

    replay = WorkflowReplay(tmp_path)
    assert replay.candidate("legacy") is None
