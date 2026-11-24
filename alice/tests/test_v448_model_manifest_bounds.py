import hashlib
from alice.voice.model_manifest import MAX_MODEL_ARTIFACTS, verify_local_model_manifest


def entry(name, path, data=b"weights"):
    return {"name": name, "path": path, "sha256": hashlib.sha256(data).hexdigest()}


def test_manifest_entry_count_is_bounded(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    r = verify_local_model_manifest(root, [entry(f"m{i}", f"m{i}.bin") for i in range(MAX_MODEL_ARTIFACTS + 1)])
    assert not r.ok and r.reason == "artifact_manifest_too_large"
    assert r.checked == 0


def test_duplicate_names_are_rejected_case_insensitively(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "a.bin").write_bytes(b"weights")
    (root / "b.bin").write_bytes(b"weights")
    r = verify_local_model_manifest(root, [entry("Voice", "a.bin"), entry("voice", "b.bin")])
    assert not r.ok and r.failed == 1
    assert r.artifacts[1].reason == "duplicate_artifact_name"


def test_duplicate_paths_are_rejected_case_insensitively(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "voice.bin").write_bytes(b"weights")
    r = verify_local_model_manifest(root, [entry("one", "voice.bin"), entry("two", "VOICE.BIN")])
    assert not r.ok and r.artifacts[1].reason == "duplicate_artifact_path"


def test_windows_absolute_and_backslash_paths_are_rejected(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    for unsafe in (r"C:\\models\\voice.bin", r"folder\\voice.bin", "//server/share/model.bin"):
        r = verify_local_model_manifest(root, [entry("voice", unsafe)])
        assert not r.ok and r.artifacts[0].reason == "artifact_path_not_relative_safe"


def test_overlong_metadata_is_rejected(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    r = verify_local_model_manifest(root, [entry("n" * 161, "voice.bin")])
    assert not r.ok and r.artifacts[0].reason == "artifact_metadata_invalid"
