from alice.voice.local_engine import LocalVoiceReadiness
from alice.voice.startup_guard import VoiceStartupGuard


def test_local_ready_is_primary():
    local = LocalVoiceReadiness(True, "local", True, True, "local_engine_ready")
    r = VoiceStartupGuard().evaluate(local, True)
    assert r.ready and r.primary == "local" and r.fallback == "sapi"


def test_sapi_is_local_fallback_when_local_engine_unready():
    local = LocalVoiceReadiness(False, "local", True, False, "generation_probe_failed")
    r = VoiceStartupGuard().evaluate(local, True)
    assert r.ready and r.primary == "sapi" and r.fallback == "sapi"


def test_no_verified_voice_path_stops_startup():
    local = LocalVoiceReadiness(False, None, False, False, "local_engine_missing")
    r = VoiceStartupGuard().evaluate(local, False)
    assert not r.ready and r.reason == "no_verified_voice_path"


def test_local_ready_does_not_require_sapi():
    local = LocalVoiceReadiness(True, "local", True, True, "local_engine_ready")
    r = VoiceStartupGuard().evaluate(local, False)
    assert r.ready and r.primary == "local" and r.fallback is None
