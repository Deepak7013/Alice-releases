import json
from alice.engineering.local_governor import LocalEngineeringGovernor


def test_local_first_selects_ready_local_model(tmp_path, monkeypatch):
    monkeypatch.setenv("ALICE_SELF_ENGINEER_LOCAL_FIRST", "1")
    monkeypatch.setenv("ALICE_SELF_ENGINEER_REQUIRE_LOCAL", "0")
    monkeypatch.setenv("ALICE_SELF_ENGINEER_ALLOW_REMOTE_FALLBACK", "1")
    g = LocalEngineeringGovernor(tmp_path)
    r = g.route({"reachable": True, "model_available": True, "model": "llama3.2:latest"})
    assert r.mode == "local"
    assert r.local_model == "llama3.2:latest"
    assert r.remote_fallback_allowed is True


def test_require_local_blocks_when_model_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("ALICE_SELF_ENGINEER_REQUIRE_LOCAL", "1")
    g = LocalEngineeringGovernor(tmp_path)
    r = g.route({"reachable": False, "model_available": False, "model": "llama3.2:latest"})
    assert r.mode == "blocked"
    assert r.remote_fallback_allowed is False


def test_remote_fallback_is_explicitly_policy_controlled(tmp_path, monkeypatch):
    monkeypatch.setenv("ALICE_SELF_ENGINEER_LOCAL_FIRST", "1")
    monkeypatch.setenv("ALICE_SELF_ENGINEER_REQUIRE_LOCAL", "0")
    monkeypatch.setenv("ALICE_SELF_ENGINEER_ALLOW_REMOTE_FALLBACK", "0")
    g = LocalEngineeringGovernor(tmp_path)
    r = g.route({"reachable": False, "model_available": False, "model": "local"})
    assert r.mode == "blocked"


def test_routing_audit_contains_no_secret_fields(tmp_path):
    g = LocalEngineeringGovernor(tmp_path)
    r = g.route({"reachable": True, "model_available": True, "model": "local"})
    g.record(r, outcome="test")
    row = json.loads(g.audit_path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["outcome"] == "test"
    assert "api_key" not in row
    assert "token" not in row
