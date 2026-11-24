from pathlib import Path
import pytest


def bare_voice():
    from alice.voice.voice import Voice
    voice = Voice.__new__(Voice)
    voice._voice_mode = "sapi"
    voice._selected_name = ""
    voice._neural_voice = ""
    voice._speech_generation = 0
    voice._speech_generation_lock = __import__("threading").Lock()
    voice._speech_queue = __import__("queue").Queue()
    voice._voice_enabled = True
    voice._last_error = ""
    voice._last_provider = ""
    voice._spoken_count = 0
    voice._failure_count = 0
    voice.settings_path = Path("unused")
    voice.continuity = type("Continuity", (), {"remember": lambda *a, **k: None})()
    voice.stop = lambda: None
    voice._save = lambda: None
    return voice


def test_current_voice_never_reports_arbitrary_first_male_voice():
    voice = bare_voice()
    voice.list_voices = lambda: [
        {"id": "david", "name": "David", "gender": "Male"},
        {"id": "zira", "name": "Zira", "gender": "Female"},
    ]
    assert voice.current_voice()["id"] == "zira"


def test_current_voice_returns_none_when_only_male_voice_is_installed():
    voice = bare_voice()
    voice.list_voices = lambda: [{"id": "david", "name": "David", "gender": "Male"}]
    assert voice.current_voice() is None


def test_saved_male_voice_is_not_reported_as_current():
    voice = bare_voice()
    voice._selected_name = "david"
    voice.list_voices = lambda: [{"id": "david", "name": "David", "gender": "Male"}]
    assert voice.current_voice() is None


def test_select_voice_rejects_male_and_unknown_gender():
    voice = bare_voice()
    voice.list_voices = lambda: [
        {"id": "david", "name": "David", "gender": "Male"},
        {"id": "mystery", "name": "Unknown Voice", "gender": ""},
    ]
    with pytest.raises(ValueError, match="female voices"):
        voice.select_voice("david")
    with pytest.raises(ValueError, match="female voices"):
        voice.select_voice("mystery")


def test_select_voice_accepts_confirmed_female_voice():
    voice = bare_voice()
    voice.list_voices = lambda: [{"id": "zira", "name": "Zira", "gender": "Female"}]
    selected = voice.select_voice("zira")
    assert selected["id"] == "zira"
    assert voice._selected_name == "zira"
    assert voice._voice_mode == "sapi"


def test_unknown_neural_profile_does_not_fall_through_to_sapi():
    voice = bare_voice()
    voice._voice_mode = "neural"
    voice._neural_voice = "unrecognized-neural-id"
    voice.list_voices = lambda: [{"id": "david", "name": "David", "gender": "Male"}]
    assert voice.current_voice() is None
