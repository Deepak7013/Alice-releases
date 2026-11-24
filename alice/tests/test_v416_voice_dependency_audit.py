from alice.voice.dependency_audit import VoiceDependencyAuditGate


class Local:
    name = "alice_local_voice"
    local_owned = True
    remote_dependency = False


class Remote:
    name = "remote_tts"
    local_owned = False
    remote_dependency = True


def test_local_provider_is_admitted():
    r = VoiceDependencyAuditGate().evaluate(Local())
    assert r.allowed and r.local_owned and not r.remote_dependency


def test_remote_provider_is_blocked_when_local_is_required():
    r = VoiceDependencyAuditGate().evaluate(Remote())
    assert not r.allowed and r.reason == "local_ownership_required"


def test_remote_provider_can_be_described_without_being_local_owned():
    r = VoiceDependencyAuditGate().evaluate(Remote(), require_local=False)
    assert r.allowed and not r.local_owned and r.remote_dependency


def test_missing_provider_is_blocked():
    r = VoiceDependencyAuditGate().evaluate(None)
    assert not r.allowed and r.reason == "provider_missing"


def test_ambiguous_provider_is_not_admitted_as_local():
    class Ambiguous:
        name = "unknown_voice"
    r = VoiceDependencyAuditGate().evaluate(Ambiguous())
    assert not r.allowed and r.reason == "local_ownership_required"
