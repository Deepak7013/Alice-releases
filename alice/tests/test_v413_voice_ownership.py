from alice.voice.ownership_policy import LocalVoiceOwnershipPolicy


def test_local_voice_is_primary_and_sapi_is_fallback():
    r = LocalVoiceOwnershipPolicy().evaluate(local_ready=True, fallback_ready=True)
    assert r.allowed and r.primary == "local" and r.fallback == "sapi"


def test_cloud_or_non_local_primary_is_forbidden():
    r = LocalVoiceOwnershipPolicy().evaluate(local_ready=True, fallback_ready=True, requested_primary="cloud")
    assert not r.allowed and r.reason == "non_local_primary_forbidden"


def test_sapi_fallback_keeps_voice_available_if_local_is_not_ready():
    r = LocalVoiceOwnershipPolicy().evaluate(local_ready=False, fallback_ready=True)
    assert r.allowed and r.primary == "sapi"


def test_no_voice_path_is_blocked():
    r = LocalVoiceOwnershipPolicy().evaluate(local_ready=False, fallback_ready=False)
    assert not r.allowed and r.reason == "no_local_voice_path"


def test_local_path_does_not_require_fallback():
    r = LocalVoiceOwnershipPolicy().evaluate(local_ready=True, fallback_ready=False)
    assert r.allowed and r.primary == "local" and r.fallback is None
