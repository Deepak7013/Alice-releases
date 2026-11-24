from alice.actions import ActionEngine, ActionStatus, ActionStore


def test_action_lifecycle_requires_approval_and_verification(tmp_path):
    engine = ActionEngine(ActionStore(tmp_path))
    record = engine.plan("publish")
    try:
        engine.execute(record.action_id, lambda: "done")
        assert False
    except PermissionError:
        pass
    engine.approve(record.action_id)
    record = engine.execute(record.action_id, lambda: "done")
    assert record.status == ActionStatus.EXECUTED
    record = engine.verify(record.action_id, lambda result: result == "done")
    assert record.status == ActionStatus.VERIFIED


def test_failed_execution_is_recorded(tmp_path):
    engine = ActionEngine(ActionStore(tmp_path))
    record = engine.plan("send_email")
    engine.approve(record.action_id)
    record = engine.execute(record.action_id, lambda: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    assert record.status == ActionStatus.FAILED
    assert "provider unavailable" in record.error


def test_verification_failure_does_not_claim_success(tmp_path):
    engine = ActionEngine(ActionStore(tmp_path))
    record = engine.plan("delete")
    engine.approve(record.action_id)
    engine.execute(record.action_id, lambda: {"deleted": True})
    record = engine.verify(record.action_id, lambda result: False)
    assert record.status == ActionStatus.FAILED
    assert record.verification == "verification_failed"


def test_action_persists_across_store_instances(tmp_path):
    engine = ActionEngine(ActionStore(tmp_path))
    record = engine.plan("purchase")
    engine.approve(record.action_id)
    loaded = ActionStore(tmp_path).get(record.action_id)
    assert loaded.approved is True
    assert loaded.status == ActionStatus.APPROVED
