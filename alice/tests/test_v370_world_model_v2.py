from alice.world.model import WorldModel

def test_world_observation_provenance_confidence_and_truth(tmp_path):
    w=WorldModel(tmp_path)
    w.observe("pc","active_window","ALICE",source="windows",confidence=0.95,ttl_seconds=60)
    result=w.truth("pc","active_window")
    assert result["known"] is True
    assert result["value"] == "ALICE"
    assert result["source"] == "windows"
    assert result["confidence"] == 0.95
    assert result["conflict"] is False

def test_world_model_detects_fresh_conflicting_observations(tmp_path):
    w=WorldModel(tmp_path)
    w.observe("browser","url","https://a.example",source="browser_a",confidence=0.7,ttl_seconds=60)
    w.observe("browser","url","https://b.example",source="browser_b",confidence=0.8,ttl_seconds=60)
    truth=w.truth("browser","url")
    assert truth["value"] == "https://b.example"
    assert truth["conflict"] is True
    assert len(w.conflicts("browser")) == 1

def test_world_model_stale_observation_is_not_current_truth(tmp_path):
    w=WorldModel(tmp_path)
    w.observe("environment","mode","temporary",source="test",confidence=1.0,ttl_seconds=0)
    assert w.truth("environment","mode")["known"] is False

def test_entity_observations_are_queryable(tmp_path):
    w=WorldModel(tmp_path)
    w.set_entity("android","phone-1",{"battery":91},source="adb",confidence=0.99,ttl_seconds=60)
    result=w.truth("android","battery",entity_id="phone-1")
    assert result["value"] == 91
    assert result["source"] == "adb"
