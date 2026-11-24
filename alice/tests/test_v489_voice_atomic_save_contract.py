import json
from pathlib import Path

def test_voice_save_uses_atomic_replace_and_fsync():
    source = (Path(__file__).parents[1] / "voice" / "voice.py").read_text(encoding="utf-8")
    assert "os.replace(tmp, self.settings_path)" in source
    assert "os.fsync(stream.fileno())" in source
    assert "json.dump(payload, stream, indent=2, ensure_ascii=False)" in source

def test_voice_default_policy_is_aria_and_preserves_explicit_choice():
    from alice.voice.default_voice_policy import apply_default_voice
    fresh = apply_default_voice({})
    assert fresh["neural_voice"] == "en-US-AriaNeural"
    assert fresh["voice_name"] == "Alice US – Aria"
    explicit = {"mode":"neural", "neural_voice":"en-US-JennyNeural", "voice_name":"My saved voice"}
    assert apply_default_voice(explicit) == explicit | {"enabled": True}
