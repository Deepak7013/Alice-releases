from alice.voice.engine_registry import LocalVoiceEngineRegistry
from alice.voice.runtime_router import LocalVoiceRuntimeRouter


class LocalEngine:
    name = "test_local_neural"
    offline = True
    local_owned = True
    remote_dependency = False
    def __init__(self, result=True, raises=False):
        self.result = result
        self.raises = raises
        self.calls = []
    def can_generate(self, text):
        return bool(text.strip())
    def speak(self, text):
        self.calls.append(text)
        if self.raises:
            raise RuntimeError("simulated engine failure")
        return self.result


def _registry(engine):
    registry = LocalVoiceEngineRegistry()
    assert registry.register(engine).admitted
    return registry


def test_runtime_router_prefers_local_neural_engine():
    engine = LocalEngine()
    fallback_calls = []
    router = LocalVoiceRuntimeRouter(_registry(engine), fallback=lambda text: fallback_calls.append(text) or True)
    result = router.speak("Hello from ALICE")
    assert result.spoken and result.provider == "test_local_neural"
    assert result.local_attempted and not result.fallback_attempted
    assert engine.calls == ["Hello from ALICE"] and fallback_calls == []


def test_runtime_router_falls_back_when_local_engine_returns_false():
    engine = LocalEngine(result=False)
    fallback_calls = []
    router = LocalVoiceRuntimeRouter(_registry(engine), fallback=lambda text: fallback_calls.append(text) or True)
    result = router.speak("Hello")
    assert result.spoken and result.provider == "sapi_fallback"
    assert result.local_attempted and result.fallback_attempted
    assert fallback_calls == ["Hello"]


def test_runtime_router_falls_back_when_local_engine_raises():
    engine = LocalEngine(raises=True)
    router = LocalVoiceRuntimeRouter(_registry(engine), fallback=lambda text: True)
    result = router.speak("Hello")
    assert result.spoken and result.reason == "local_fallback_played"


def test_runtime_router_does_not_call_fallback_for_empty_text():
    engine = LocalEngine()
    calls = []
    router = LocalVoiceRuntimeRouter(_registry(engine), fallback=lambda text: calls.append(text) or True)
    result = router.speak("  ")
    assert not result.spoken and result.reason == "text_missing_after_preparation"
    assert calls == [] and engine.calls == []


def test_runtime_router_fails_closed_when_both_local_paths_fail():
    engine = LocalEngine(result=False)
    router = LocalVoiceRuntimeRouter(_registry(engine), fallback=lambda text: False)
    result = router.speak("Hello")
    assert not result.spoken and result.reason == "local_fallback_failed"
    assert result.fallback_attempted


def test_runtime_router_bounds_text():
    import pytest
    with pytest.raises(ValueError):
        LocalVoiceRuntimeRouter(LocalVoiceEngineRegistry(), max_text_chars=0)
    router = LocalVoiceRuntimeRouter(LocalVoiceEngineRegistry(), max_text_chars=3)
    result = router.speak("long")
    assert not result.spoken and result.reason == "text_too_large"


def test_runtime_router_prepares_markup_urls_and_emoji_before_local_speech():
    engine = LocalEngine()
    router = LocalVoiceRuntimeRouter(_registry(engine), fallback=lambda text: True)
    result = router.speak("**Hello** 😊 https://example.com world")
    assert result.spoken
    assert engine.calls == ["Hello world"]


def test_runtime_router_prepares_text_before_female_sapi_fallback():
    engine = LocalEngine(result=False)
    fallback_calls = []
    router = LocalVoiceRuntimeRouter(_registry(engine), fallback=lambda text: fallback_calls.append(text) or True)
    result = router.speak("Hi! 🎉 www.example.com **Alice**")
    assert result.spoken
    assert engine.calls == ["Hi! Alice"]
    assert fallback_calls == ["Hi! Alice"]


def test_runtime_router_does_not_speak_emoji_or_markup_only_input():
    engine = LocalEngine()
    fallback_calls = []
    router = LocalVoiceRuntimeRouter(_registry(engine), fallback=lambda text: fallback_calls.append(text) or True)
    result = router.speak("😊 🎉 ** __ ~~")
    assert not result.spoken and result.reason == "text_missing_after_preparation"
    assert engine.calls == [] and fallback_calls == []
