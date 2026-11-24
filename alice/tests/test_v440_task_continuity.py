from alice.horizon.task_continuity import TaskContinuityStore

def test_task_survives_reload_and_resumes_from_verified_checkpoint(tmp_path):
    s = TaskContinuityStore(tmp_path)
    t = s.create("finish project", next_action="run tests")
    s.checkpoint(t["task_id"], label="build", state={"step": 2}, verified=True)
    s2 = TaskContinuityStore(tmp_path)
    d = s2.resume(t["task_id"])
    assert d.resumable and d.checkpoint["state"]["step"] == 2

def test_unverified_checkpoint_cannot_authorize_resume(tmp_path):
    s = TaskContinuityStore(tmp_path)
    t = s.create("finish project")
    s.checkpoint(t["task_id"], label="build", state={"step": 2}, verified=False)
    d = s.resume(t["task_id"])
    assert not d.resumable and d.reason == "no_verified_checkpoint"

def test_completed_task_cannot_resume(tmp_path):
    s = TaskContinuityStore(tmp_path)
    t = s.create("finish project")
    s.checkpoint(t["task_id"], label="done", state={}, verified=True)
    s.set_status(t["task_id"], "completed")
    d = s.resume(t["task_id"])
    assert not d.resumable and d.reason == "task_not_active"


def test_tampered_persisted_checkpoint_state_fails_closed(tmp_path):
    s = TaskContinuityStore(tmp_path)
    t = s.create("finish project")
    s.checkpoint(t["task_id"], label="build", state={"step": 2}, verified=True)
    import json
    persisted = json.loads(s.path.read_text(encoding="utf-8"))
    persisted[t["task_id"]]["checkpoints"][0]["state"]["step"] = 99
    s.path.write_text(json.dumps(persisted), encoding="utf-8")
    decision = TaskContinuityStore(tmp_path).resume(t["task_id"])
    assert not decision.resumable
    assert decision.reason == "no_valid_verified_checkpoint"


def test_legacy_checkpoint_without_integrity_receipt_fails_closed(tmp_path):
    s = TaskContinuityStore(tmp_path)
    t = s.create("finish project")
    s.checkpoint(t["task_id"], label="build", state={"step": 2}, verified=True)
    raw = __import__("json").loads(s.path.read_text(encoding="utf-8"))
    raw[t["task_id"]]["checkpoints"][0].pop("integrity_sha256")
    s.path.write_text(__import__("json").dumps(raw), encoding="utf-8")
    decision = TaskContinuityStore(tmp_path).resume(t["task_id"])
    assert not decision.resumable
    assert decision.reason == "no_valid_verified_checkpoint"


def test_corrupt_store_is_preserved_and_becomes_read_only(tmp_path):
    import pytest
    store = TaskContinuityStore(tmp_path)
    t = store.create("keep original bytes")
    original = store.path.read_text(encoding="utf-8")
    store.path.write_text("{ definitely not json", encoding="utf-8")
    damaged = store.path.read_bytes()
    recovered = TaskContinuityStore(tmp_path)
    assert recovered.load_error
    assert not recovered.resume(t["task_id"]).resumable
    with pytest.raises(RuntimeError, match="read_only_after_load_error"):
        recovered.create("must not overwrite evidence")
    assert store.path.read_bytes() == damaged
    assert original != damaged


def test_oversized_checkpoint_state_is_rejected_without_persisting(tmp_path):
    import pytest
    store = TaskContinuityStore(tmp_path)
    task = store.create("bounded state")
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="checkpoint_state_too_large"):
        store.checkpoint(task["task_id"], label="too big", state={"payload": "x" * 70000}, verified=True)
    assert store.path.read_bytes() == before
    assert store.get(task["task_id"])["checkpoints"] == []


def test_invalid_nonfinite_checkpoint_state_is_rejected(tmp_path):
    import pytest
    store = TaskContinuityStore(tmp_path)
    task = store.create("finite JSON only")
    with pytest.raises(ValueError):
        store.checkpoint(task["task_id"], label="NaN", state={"value": float("nan")}, verified=True)
    assert store.get(task["task_id"])["checkpoints"] == []


def test_active_tasks_are_never_silently_evicted_at_capacity(tmp_path):
    import pytest
    store = TaskContinuityStore(tmp_path, max_tasks=1)
    first = store.create("first active task")
    with pytest.raises(ValueError, match="active_task_capacity_reached"):
        store.create("second active task")
    assert store.get(first["task_id"]) is not None
    assert len(store.tasks) == 1


def test_terminal_task_may_be_evicted_before_active_task(tmp_path):
    store = TaskContinuityStore(tmp_path, max_tasks=1)
    first = store.create("terminal task")
    store.set_status(first["task_id"], "completed")
    second = store.create("active task")
    assert store.get(second["task_id"]) is not None
    assert store.get(first["task_id"]) is None
    restored = TaskContinuityStore(tmp_path, max_tasks=1)
    assert restored.get(second["task_id"]) is not None
