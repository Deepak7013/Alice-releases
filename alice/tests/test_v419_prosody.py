from alice.voice.prosody import ProsodyPlanner


def test_natural_profile_is_stable():
    r = ProsodyPlanner().plan("natural")
    assert r.valid and r.rate == 1.0 and r.pause_ms == 180


def test_urgency_is_bounded_and_changes_delivery():
    base = ProsodyPlanner().plan("natural")
    urgent = ProsodyPlanner().plan("natural", urgency=1.0)
    assert urgent.valid and urgent.rate > base.rate
    assert urgent.pause_ms < base.pause_ms
    assert urgent.emphasis == "strong" and urgent.emotion == "urgent"


def test_unknown_profile_is_rejected():
    r = ProsodyPlanner().plan("unknown")
    assert not r.valid and r.reason == "unknown_profile"


def test_profile_names_are_case_insensitive():
    assert ProsodyPlanner().plan("Professional").valid
