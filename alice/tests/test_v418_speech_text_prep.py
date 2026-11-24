from alice.voice.text_prep import prepare_for_speech, apply_pronunciation


def test_markup_urls_and_emoji_are_not_spoken_literally():
    value = prepare_for_speech("**Hello** 😊 https://example.com")
    assert value == "Hello"
    assert "smiling" not in value.lower()


def test_normalization_preserves_sentence_text():
    value = prepare_for_speech("  Alice   is ready.\nNext step!  ")
    assert value == "Alice is ready. Next step!"


def test_pronunciation_dictionary_applies_longest_phrases_first():
    value = apply_pronunciation("Use OpenAI API and OpenAI today.", {"OpenAI API": "Open A I A P I", "OpenAI": "Open A I"})
    assert value == "Use Open A I A P I and Open A I today."


def test_empty_input_is_safe():
    assert prepare_for_speech(None) == ""
    assert apply_pronunciation("") == ""
