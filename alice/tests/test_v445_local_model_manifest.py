import hashlib
from alice.voice.model_manifest import verify_local_model_manifest

def entry(name, path, data):
    return {"name":name,"path":path,"sha256":hashlib.sha256(data).hexdigest()}

def test_valid_local_artifact_verifies(tmp_path):
    root=tmp_path/"models"; root.mkdir(); payload=b"local-model-test"; (root/"voice.bin").write_bytes(payload)
    r=verify_local_model_manifest(root,[entry("voice","voice.bin",payload)])
    assert r.ok and r.checked==1 and r.failed==0 and r.artifacts[0].reason=="artifact_verified"

def test_hash_mismatch_fails_closed(tmp_path):
    root=tmp_path/"models"; root.mkdir(); (root/"voice.bin").write_bytes(b"actual")
    r=verify_local_model_manifest(root,[entry("voice","voice.bin",b"expected")])
    assert not r.ok and r.failed==1 and r.artifacts[0].reason=="artifact_hash_mismatch"

def test_missing_artifact_is_reported(tmp_path):
    root=tmp_path/"models"; root.mkdir()
    r=verify_local_model_manifest(root,[entry("voice","missing.bin",b"expected")])
    assert not r.ok and r.artifacts[0].reason=="artifact_missing"

def test_parent_traversal_is_rejected(tmp_path):
    root=tmp_path/"models"; root.mkdir(); payload=b"outside"; (tmp_path/"outside.bin").write_bytes(payload)
    r=verify_local_model_manifest(root,[entry("escape","../outside.bin",payload)])
    assert not r.ok and r.artifacts[0].reason=="artifact_path_not_relative_safe"

def test_symlink_escape_is_rejected_when_supported(tmp_path):
    root=tmp_path/"models"; root.mkdir(); outside=tmp_path/"outside.bin"; outside.write_bytes(b"x")
    try: (root/"link.bin").symlink_to(outside)
    except (OSError,NotImplementedError): return
    r=verify_local_model_manifest(root,[entry("escape","link.bin",b"x")])
    assert not r.ok and r.artifacts[0].reason=="artifact_path_escape"

def test_invalid_manifest_and_digest_rejected(tmp_path):
    root=tmp_path/"models"; root.mkdir()
    assert verify_local_model_manifest(root,[]).reason=="artifact_manifest_empty_or_invalid"
    r=verify_local_model_manifest(root,[{"name":"x","path":"x.bin","sha256":"bad"}])
    assert not r.ok and r.artifacts[0].reason=="artifact_metadata_invalid"
