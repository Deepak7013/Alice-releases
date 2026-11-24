from alice.voice.continuity import VoiceContinuityGuard


def test_voice_fingerprint_is_stable(tmp_path):
    g = VoiceContinuityGuard(tmp_path / "voice_continuity.json")
    saved = g.remember(voice_id="zira-id", name="Microsoft Zira", mode="sapi")
    result = g.compare(voice_id="zira-id", name="Microsoft Zira", mode="sapi")
    assert result["ok"]
    assert result["current"] == saved["fingerprint"]


def test_voice_change_is_detected(tmp_path):
    g = VoiceContinuityGuard(tmp_path / "voice_continuity.json")
    g.remember(voice_id="zira-id", name="Microsoft Zira", mode="sapi")
    result = g.compare(voice_id="other", name="Other Voice", mode="sapi")
    assert not result["ok"]
    assert result["state"] == "changed"
