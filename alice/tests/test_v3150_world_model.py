import time
from alice.world.model import WorldModel

def test_world_model_typed_state_and_freshness(tmp_path):
    w=WorldModel(tmp_path)
    w.update("pc", {"running_apps":["Alice"]}, source="desktop", ttl_seconds=60)
    assert w.snapshot()["pc"]["running_apps"] == ["Alice"]
    assert w.freshness("pc")["fresh"]
    w.set_entity("android","phone-1",{"battery":91},source="adb",ttl_seconds=60)
    assert w.get_entity("android","phone-1")["data"]["battery"] == 91

def test_world_model_merge_preserves_state(tmp_path):
    w=WorldModel(tmp_path)
    w.update("browser", {"url":"https://example.com","title":"Example"})
    w.merge("browser", {"title":"New title"}, source="browser")
    assert w.snapshot()["browser"]["url"] == "https://example.com"
    assert w.snapshot()["browser"]["title"] == "New title"

def test_world_model_stale_state(tmp_path):
    w=WorldModel(tmp_path)
    w.update("environment", {"mode":"test"}, ttl_seconds=0)
    time.sleep(0.01)
    assert "environment" in w.stale_domains()

def test_planning_summary_is_request_relevant_and_omits_private_observation_values(tmp_path):
    import json
    w=WorldModel(tmp_path)
    w.update("android",{"serial":"DEVICE-PRIVATE-987","connected":True},source="adb",ttl_seconds=60)
    w.update("browser",{"url":"https://private.example/path?token=SECRET_VALUE"},source="browser",ttl_seconds=60)
    summary=w.planning_summary("connect to my phone",max_chars=1200)
    payload=json.loads(summary)
    assert payload["trust"]=="observation_only"
    assert payload["policy"].startswith("metadata_only")
    assert [item["domain"] for item in payload["domains"]]==["android"]
    assert payload["domains"][0]["known"] is True
    assert payload["domains"][0]["fresh"] is True
    assert "DEVICE-PRIVATE-987" not in summary
    assert "private.example" not in summary and "SECRET_VALUE" not in summary
    assert len(summary)<=1200

def test_planning_summary_retains_staleness_and_omits_unrelated_domains(tmp_path):
    import json,time
    w=WorldModel(tmp_path)
    w.update("android",{"serial":"DEVICE-PRIVATE-987"},source="adb",ttl_seconds=0)
    time.sleep(0.01)
    payload=json.loads(w.planning_summary("message on my phone"))
    assert payload["domains"][0]["fresh"] is False
    assert payload["domains"][0]["age_seconds"] is not None
    assert w.planning_summary("summarize the weather") == ""
