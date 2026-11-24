from alice.cognitive.workspace import CognitiveWorkspaceStore


def test_workspace_tracks_core_task_state(tmp_path):
    s = CognitiveWorkspaceStore(tmp_path)
    w = s.create("repair the failing build", mode="debug", unknowns=["root cause"])
    assert w["goal"] == "repair the failing build"
    assert w["unknowns"] == ["root cause"]
    assert s.current()["workspace_id"] == w["workspace_id"]


def test_workspace_records_evidence_failures_decisions(tmp_path):
    s = CognitiveWorkspaceStore(tmp_path)
    w = s.create("test provider recovery")
    wid = w["workspace_id"]
    s.add(wid, "evidence", "tiny request succeeded")
    s.add(wid, "failures", "402 at oversized token budget")
    s.add(wid, "decisions", "lower budget and retry once")
    got = s.get(wid)
    assert got["evidence"] == ["tiny request succeeded"]
    assert got["failures"] == ["402 at oversized token budget"]
    assert got["decisions"] == ["lower budget and retry once"]


def test_workspace_rejects_invalid_mode_and_status(tmp_path):
    s = CognitiveWorkspaceStore(tmp_path)
    try:
        s.create("x", mode="unsafe_mode")
        assert False
    except ValueError:
        pass
    w = s.create("x")
    try:
        s.update(w["workspace_id"], status="magic")
        assert False
    except ValueError:
        pass


def test_workspace_persists_and_completes(tmp_path):
    s = CognitiveWorkspaceStore(tmp_path)
    w = s.create("finish package")
    wid = w["workspace_id"]
    s.update(wid, current_step=3, selected_plan={"steps": ["build", "test"]})
    done = s.complete(wid, "493 tests passed")
    assert done["status"] == "completed"
    assert done["outcome"] == "493 tests passed"
    assert s.current() is None
    s2 = CognitiveWorkspaceStore(tmp_path)
    assert s2.get(wid)["status"] == "completed"


def test_reasoning_engine_exposes_task_workspace(tmp_path):
    from alice.reasoning.engine import ReasoningEngine
    r = ReasoningEngine(root=tmp_path)
    w = r.begin_task("analyze a failing test", mode="debug")
    r.add_evidence(w["workspace_id"], "test reproduced")
    r.add_failure(w["workspace_id"], "provider timeout")
    r.add_decision(w["workspace_id"], "use local deterministic path")
    state = r.task_state(w["workspace_id"])
    assert state["mode"] == "debug"
    assert state["evidence"] == ["test reproduced"]
    assert state["failures"] == ["provider timeout"]
    assert state["decisions"] == ["use local deterministic path"]
