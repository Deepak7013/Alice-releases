from alice.voice.engine_registry import LocalVoiceEngineRegistry


class LocalEngine:
    name = "local-test"
    offline = True

    def can_generate(self, text):
        return bool(text)


def test_registry_admits_ready_local_engine():
    registry = LocalVoiceEngineRegistry()
    result = registry.register(LocalEngine())
    assert result.admitted is True
    assert registry.available() == ("local-test",)


def test_registry_rejects_nonlocal_engine():
    class Remote:
        name = "remote"
        offline = False

        def can_generate(self, text):
            return True

    result = LocalVoiceEngineRegistry().register(Remote())
    assert result.admitted is False
    assert result.reason == "offline_capability_required"


def test_registry_preferred_selection_is_deterministic():
    registry = LocalVoiceEngineRegistry()
    first = LocalEngine()
    first.name = "zeta"
    second = LocalEngine()
    second.name = "alpha"
    registry.register(first)
    registry.register(second)
    assert registry.select("zeta") is first
    assert registry.select("missing") is second


def test_registry_returns_none_when_empty():
    assert LocalVoiceEngineRegistry().select() is None
