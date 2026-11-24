from alice.voice.delivery_sync import synchronize_response


def test_voice_gets_exact_display_text():
    result = synchronize_response("Hello, ALICE.")
    assert result.synchronized is True
    assert result.speak is True
    assert result.voice_text == result.display_text


def test_empty_response_never_triggers_voice():
    result = synchronize_response("  ")
    assert result.speak is False
    assert result.voice_text == ""
    assert result.reason == "empty_response_no_speech"


def test_text_only_mode_never_triggers_voice():
    result = synchronize_response("Keep this visible only.", voice_enabled=False)
    assert result.speak is False
    assert result.display_text == "Keep this visible only."
    assert result.voice_text == ""
    assert result.synchronized is True
