from alice.voice.neural import NeuralVoiceProvider


def test_sentence_split_preserves_all_words_and_punctuation():
    source = "Hello there. This is Alice! Are you ready?"
    chunks = NeuralVoiceProvider.split_for_early_audio(source)
    assert chunks == ["Hello there.", "This is Alice!", "Are you ready?"]
    assert " ".join(chunks).replace("  ", " ") == source


def test_long_sentence_is_split_at_word_boundaries_without_loss():
    source = ("word " * 100).strip() + "."
    chunks = NeuralVoiceProvider.split_for_early_audio(source, max_chars=80)
    assert len(chunks) > 1
    assert all(len(chunk) <= 80 for chunk in chunks)
    assert " ".join(chunks).replace(" .", ".") == source


def test_empty_speech_returns_no_chunks():
    assert NeuralVoiceProvider.split_for_early_audio("  \n ") == []


def test_chunk_limit_is_validated():
    import pytest
    with pytest.raises(ValueError):
        NeuralVoiceProvider.split_for_early_audio("hello", max_chars=10)


def test_diagnostic_cache_returns_copy(monkeypatch, tmp_path):
    provider = NeuralVoiceProvider(tmp_path)
    monkeypatch.setattr(provider, "available", lambda: True)
    monkeypatch.setattr("alice.voice.neural.socket.getaddrinfo", lambda *a, **k: object())
    class Sock:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr("alice.voice.neural.socket.create_connection", lambda *a, **k: Sock())
    NeuralVoiceProvider._diagnostic_cache.clear()
    first = provider.diagnose_voice("en-US-AriaNeural", refresh=True)
    first["ok"] = False
    second = provider.diagnose_voice("en-US-AriaNeural")
    assert second["ok"] is True
    assert second["endpoint"] is True


def test_neural_failure_calls_verified_female_fallback_only():
    import threading
    from alice.voice.voice import Voice
    voice = Voice.__new__(Voice)
    voice._voice_mode = "neural"
    voice._neural_voice = "en-US-AriaNeural"
    voice._speech_generation = 0
    voice._speech_generation_lock = threading.Lock()
    voice._active_speech_cancel = threading.Event()
    voice._last_error = ""
    voice._last_provider = ""
    voice._spoken_count = 0
    voice._failure_count = 0
    voice._speak_neural = lambda text: False
    calls = []
    voice._speak_sapi_female_fallback = lambda text: calls.append(text) or True
    assert voice._speak_with_recovery("Hello") is True
    assert calls == ["Hello"]
    assert voice._spoken_count == 1
