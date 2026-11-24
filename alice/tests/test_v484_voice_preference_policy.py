from alice.voice.default_voice_policy import apply_default_voice, DEFAULT_LABEL, DEFAULT_VOICE_ID

def test_fresh_settings_default_to_aria():
    settings = apply_default_voice(None)
    assert settings["voice_name"] == DEFAULT_LABEL
    assert settings["neural_voice"] == DEFAULT_VOICE_ID
    assert settings["mode"] == "neural" and settings["enabled"] is True

def test_existing_voice_choice_is_preserved():
    original = {"voice_name": "Alice UK – Sonia", "neural_voice": "en-GB-SoniaNeural", "mode": "neural", "enabled": True}
    result = apply_default_voice(original)
    assert result == original and result is not original

def test_blank_voice_fields_are_filled_without_losing_other_settings():
    result = apply_default_voice({"voice_name": " ", "neural_voice": "", "theme": "blue"})
    assert result["voice_name"] == DEFAULT_LABEL and result["neural_voice"] == DEFAULT_VOICE_ID
    assert result["theme"] == "blue"
