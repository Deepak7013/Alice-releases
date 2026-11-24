from alice.voice.natural_pauses import plan_natural_pauses

def test_empty_text_has_no_segments():
    assert plan_natural_pauses("") == []

def test_pause_metadata_preserves_order():
    got = plan_natural_pauses("Hello there. How are you?")
    assert [x["text"] for x in got] == ["Hello there.", "How are you?"]
    assert got[0]["pause_ms"] == 220
    assert got[1]["pause_ms"] == 300

def test_comma_pause_is_bounded():
    got = plan_natural_pauses("Wait, please.")
    assert got[0]["pause_ms"] == 180

def test_planner_only_returns_metadata():
    got = plan_natural_pauses("Hello.")
    assert set(got[0]) == {"text", "pause_ms"}
