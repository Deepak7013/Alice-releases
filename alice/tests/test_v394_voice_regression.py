from alice.voice.regression import verify_voice_continuity
from alice.voice.continuity import VoiceContinuityGuard

def test_uninitialized_voice_is_safe(tmp_path):
    r=verify_voice_continuity(tmp_path/"voice.json",name="Alice",mode="sapi")
    assert r.ok and r.state=="uninitialized"

def test_voice_change_is_detected(tmp_path):
    p=tmp_path/"voice.json"; VoiceContinuityGuard(p).remember(voice_id="a",name="Alice",mode="sapi")
    r=verify_voice_continuity(p,voice_id="b",name="Alice",mode="sapi")
    assert not r.ok and r.state=="changed"

def test_same_voice_is_preserved(tmp_path):
    p=tmp_path/"voice.json"; VoiceContinuityGuard(p).remember(voice_id="a",name="Alice",mode="sapi")
    r=verify_voice_continuity(p,voice_id="a",name="Alice",mode="sapi")
    assert r.ok and r.state=="preserved"
