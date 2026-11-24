import hashlib
from alice.voice.model_manifest import verify_local_model_manifest


def entry(name, path, data=b"weights"):
    return {"name": name, "path": path, "sha256": hashlib.sha256(data).hexdigest()}


def test_manifest_digest_is_present_and_stable(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "a.bin").write_bytes(b"weights")
    first = verify_local_model_manifest(root, [entry("a", "a.bin")])
    second = verify_local_model_manifest(root, [entry("a", "a.bin")])
    assert first.ok and first.manifest_digest
    assert first.manifest_digest == second.manifest_digest
    assert len(first.manifest_digest) == 64


def test_manifest_digest_is_independent_of_entry_order(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "a.bin").write_bytes(b"weights")
    (root / "b.bin").write_bytes(b"weights")
    a, b = entry("a", "a.bin"), entry("b", "b.bin")
    r1 = verify_local_model_manifest(root, [a, b])
    r2 = verify_local_model_manifest(root, [b, a])
    assert r1.manifest_digest == r2.manifest_digest


def test_manifest_digest_changes_when_metadata_changes(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "a.bin").write_bytes(b"weights")
    r1 = verify_local_model_manifest(root, [entry("a", "a.bin")])
    r2 = verify_local_model_manifest(root, [entry("renamed", "a.bin")])
    assert r1.manifest_digest != r2.manifest_digest


def test_rejected_manifest_still_has_digest_for_audit(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    r = verify_local_model_manifest(root, [{"name": "bad", "path": "../escape", "sha256": "invalid"}])
    assert not r.ok and r.manifest_digest
