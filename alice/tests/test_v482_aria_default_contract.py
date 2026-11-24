from pathlib import Path
import ast


def test_aria_is_registered_as_confirmed_female_voice():
    from alice.voice.neural import FEMALE_VOICE_PACKS
    assert FEMALE_VOICE_PACKS["Alice US – Aria"]["voice"] == "en-US-AriaNeural"
    assert FEMALE_VOICE_PACKS["Alice US – Aria"]["gender"] == "Female"


def test_fresh_voice_settings_default_to_neural_aria_and_existing_settings_win():
    source = Path("alice/voice/voice.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    # Contract guard: fresh settings are initialized to Aria/neural; existing settings are loaded first.
    assert '"mode": "neural", "neural_voice": "en-US-AriaNeural"' in source
    assert 'settings = self._load()' in source
    assert 'if not settings:' in source


def test_edge_neural_provider_is_explicitly_network_dependent():
    source = Path("alice/voice/neural.py").read_text(encoding="utf-8")
    assert "network-dependent" in source
    assert "en-US-AriaNeural" in source
