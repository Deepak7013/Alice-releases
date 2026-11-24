
import tempfile
from pathlib import Path
from alice.security.policy import SecurityPolicy, TrustLevel, SecretStore
from alice.security.verifier import CapabilityVerifier

def test_scope_is_not_trust():
    p = SecurityPolicy()
    p.grant("x", ["files.read"], TrustLevel.VERIFIED)
    assert p.authorize("x", ["files.read"])[0]
    assert not p.authorize("x", ["process.spawn"])[0]

def test_secret_not_exported_by_default():
    with tempfile.TemporaryDirectory() as d:
        s = SecretStore(Path(d) / "secrets.json")
        s.set("API_KEY", "secret")
        assert s.get("API_KEY") == "secret"
        assert s.export_env([]) == {}

def test_digest_verification():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cap.py"
        p.write_text("print('ok')")
        v = CapabilityVerifier()
        digest = v.digest_tree(p)
        result = v.verify(p, digest, TrustLevel.VERIFIED)
        assert result.verified
        assert v.activation_allowed(result)

def test_unverified_capability_blocked():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "cap.py"
        p.write_text("print('ok')")
        v = CapabilityVerifier()
        result = v.verify(p, trust=TrustLevel.UNTRUSTED)
        assert not result.verified
        assert not v.activation_allowed(result)
