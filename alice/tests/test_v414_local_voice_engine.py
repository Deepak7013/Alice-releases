from alice.voice.local_engine import LocalVoiceEngineGate


class GoodLocal:
    name = "alice_local_test_engine"
    offline = True
    def can_generate(self, text):
        return bool(text.strip())


class CloudLike:
    name = "remote_tts"
    offline = False
    def can_generate(self, text):
        return True


def test_offline_local_engine_is_admitted():
    r = LocalVoiceEngineGate().evaluate(GoodLocal(), "hello")
    assert r.ready and r.offline and r.can_generate
    assert r.engine == "alice_local_test_engine"


def test_cloud_engine_is_not_admitted_as_local():
    r = LocalVoiceEngineGate().evaluate(CloudLike(), "hello")
    assert not r.ready and r.reason == "offline_capability_required"


def test_missing_engine_is_blocked():
    r = LocalVoiceEngineGate().evaluate(None)
    assert not r.ready and r.reason == "local_engine_missing"


def test_engine_without_probe_is_blocked():
    class NoProbe:
        name = "local"
        offline = True
    r = LocalVoiceEngineGate().evaluate(NoProbe(), "hello")
    assert not r.ready and r.reason == "generation_probe_missing"


def test_failed_generation_probe_is_blocked():
    class Broken:
        name = "local"
        offline = True
        def can_generate(self, text):
            return False
    r = LocalVoiceEngineGate().evaluate(Broken(), "hello")
    assert not r.ready and r.reason == "generation_probe_failed"
