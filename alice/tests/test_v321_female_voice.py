from pathlib import Path

def test_female_voice_selection_never_falls_back_to_male():
    from alice.voice.voice import Voice
    v=Voice(root=Path(__file__).resolve().parents[2])
    v.list_voices=lambda: [{"id":"male","name":"David","gender":"Male"}]
    v.neural.available=lambda: False
    assert v.select_female_default() is None

def test_female_voice_profiles_are_declared_and_female_only():
    from alice.voice.neural import FEMALE_VOICE_PACKS
    assert len(FEMALE_VOICE_PACKS) >= 5
    assert all(v["gender"] == "Female" for v in FEMALE_VOICE_PACKS.values())

def test_voice_contract_exposes_female_only_mode():
    from alice.voice.voice import Voice
    v=Voice(root=Path(__file__).resolve().parents[2])
    v.current_voice=lambda: {"name":"Alice","gender":"Female"}
    c=v.voice_contract()
    assert c["female_only"] is True


def test_neural_female_mode_never_falls_back_to_sapi():
    from alice.voice.voice import Voice
    v=Voice(root=Path(__file__).resolve().parents[2])
    v._voice_mode="neural"; v._neural_voice="en-US-AriaNeural"
    # Deterministic safety case: only a male voice is present, so SAPI fallback must be rejected.
    v.list_voices=lambda: [{"id":"male","name":"David","gender":"Male"}]
    v._speak_neural=lambda text: (_ for _ in ()).throw(RuntimeError("offline"))
    v._speak_powershell=lambda text: (_ for _ in ()).throw(AssertionError("male SAPI fallback must not run"))
    assert v._speak_with_recovery("hello") is False
