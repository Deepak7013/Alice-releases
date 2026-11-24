from alice.actions import ActionEngine, ActionStore, ActionStatus, ExecutiveActionEngine


def test_execution_requires_verified_planning(tmp_path):
    e = ExecutiveActionEngine(ActionEngine(ActionStore(tmp_path)))
    try:
        e.prepare({"steps": [{"action": "do safe thing"}]}, planning_verified=False)
    except PermissionError:
        pass
    else:
        assert False, "unverified planning must not reach execution preparation"


def test_prepare_approve_execute_verify(tmp_path):
    e = ExecutiveActionEngine(ActionEngine(ActionStore(tmp_path)))
    ids = e.prepare({"steps": [{"action": "read workspace"}, {"action": "run tests"}]}, planning_verified=True)
    assert len(ids) == 2
    records = e.approve_all(ids)
    assert all(r.status == ActionStatus.APPROVED for r in records)
    out = e.execute_and_verify(ids, [lambda: "ok", lambda: 42], [lambda x: x == "ok", lambda x: x == 42])
    assert out.executed == 2
    assert out.verified == 2
    assert out.failed == 0
    assert "verified" in out.message.lower()


def test_failed_verification_is_not_completion(tmp_path):
    e = ExecutiveActionEngine(ActionEngine(ActionStore(tmp_path)))
    ids = e.prepare({"steps": [{"action": "change file"}]}, planning_verified=True)
    e.approve_all(ids)
    out = e.execute_and_verify(ids, [lambda: "changed"], [lambda x: False])
    assert out.executed == 1
    assert out.verified == 0
    assert out.failed == 1
    assert "do not claim completion" in out.message


def test_counts_must_match(tmp_path):
    e = ExecutiveActionEngine(ActionEngine(ActionStore(tmp_path)))
    ids = e.prepare({"steps": [{"action": "one"}]}, planning_verified=True)
    e.approve_all(ids)
    try:
        e.execute_and_verify(ids, [lambda: 1], [])
    except ValueError:
        pass
    else:
        assert False
