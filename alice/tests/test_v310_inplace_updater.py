import json
from pathlib import Path

import pytest

from alice.deployment.updater import (
    InPlaceUpdater, UpgradeError, build_manifest, is_protected, read_version, version_tuple
)


def make_install(tmp_path, version="ALICE v3.9"):
    root = tmp_path / "Alice"
    (root / "alice").mkdir(parents=True)
    (root / ".venv" / "Scripts").mkdir(parents=True)
    # The updater validation only needs the interpreter path to exist.
    # Use a regular stub file so the test works on Windows without Developer
    # Mode / SeCreateSymbolicLinkPrivilege. Execution is patched in tests that
    # reach the post-update verification step.
    (root / ".venv" / "Scripts" / "python.exe").write_bytes(b"stub")
    (root / "VERSION.txt").write_text(version + "\n", encoding="utf-8")
    (root / "alice" / "marker.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=keep\n", encoding="utf-8")
    (root / "alice_workspace").mkdir()
    (root / "alice_workspace" / "memory.json").write_text('{"keep": true}', encoding="utf-8")
    return root


def make_payload(tmp_path, version="ALICE v3.10", value="new"):
    payload = tmp_path / "payload"
    (payload / "alice").mkdir(parents=True)
    (payload / "VERSION.txt").write_text(version + "\n", encoding="utf-8")
    (payload / "alice" / "marker.py").write_text(f"VALUE = {value!r}\n", encoding="utf-8")
    (payload / "alice" / "new_feature.py").write_text("VALUE = 10\n", encoding="utf-8")
    m = build_manifest(payload, version, "ALICE v3.9")
    (payload / "upgrade_manifest.json").write_text(json.dumps(m), encoding="utf-8")
    return payload


def test_version_tuple():
    assert version_tuple("ALICE v3.10") > version_tuple("ALICE v3.9")
    assert version_tuple("v3.9") == (3, 9)


def test_protected_paths():
    assert is_protected(".env")
    assert is_protected("alice_workspace/runtime/x.json")
    assert is_protected("data/foo.txt")
    assert is_protected("alice/security/policy.py")
    assert not is_protected("alice/deployment/updater.py")


def test_manifest_hashes(tmp_path):
    payload = make_payload(tmp_path)
    import sys
    sys.path.insert(0, str(Path(__file__).parents[2]))
    m = build_manifest(payload, "ALICE v3.10", "ALICE v3.9")
    assert m["version"] == "ALICE v3.10"
    assert len(m["files"]) == 3
    assert all(len(x["sha256"]) == 64 for x in m["files"])


def test_apply_preserves_user_state(tmp_path):
    root = make_install(tmp_path)
    payload = make_payload(tmp_path)
    updater = InPlaceUpdater(root)
    # The test runner is not actually the copied python executable in this fixture,
    # so patch the test method to verify the transactional file logic.
    updater._run_tests = lambda: type("R", (), {"returncode": 0, "stdout": "1 passed", "stderr": ""})()
    result = updater.apply(payload)
    assert result["ok"]
    assert read_version(root) == "ALICE v3.10"
    assert (root / "alice" / "marker.py").read_text() == "VALUE = 'new'\n"
    assert (root / "alice" / "new_feature.py").exists()
    assert (root / ".env").read_text() == "SECRET=keep\n"
    assert (root / "alice_workspace" / "memory.json").exists()


def test_failed_update_rolls_back(tmp_path):
    root = make_install(tmp_path)
    payload = make_payload(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: type("R", (), {"returncode": 1, "stdout": "", "stderr": "boom"})()
    result = updater.apply(payload)
    assert not result["ok"] and result["rolled_back"]
    assert read_version(root) == "ALICE v3.9"
    assert (root / "alice" / "marker.py").read_text() == "VALUE = 'old'\n"
    assert not (root / "alice" / "new_feature.py").exists()


def test_post_update_test_process_ignores_inherited_provider_configuration(tmp_path, monkeypatch):
    import subprocess

    root = make_install(tmp_path)
    updater = InPlaceUpdater(root)
    monkeypatch.setenv("OPENROUTER_FREE_ONLY", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-leak-to-test-process")
    captured = {}

    def fake_run(command, **kwargs):
        if "-m" in command and "pytest" in command:
            captured.update(kwargs["env"])
        return subprocess.CompletedProcess(command, 0, "1 passed", "")

    monkeypatch.setattr("alice.deployment.updater._harden_directory", lambda path: None)
    monkeypatch.setattr("alice.deployment.updater.subprocess.run", fake_run)
    result = updater._run_tests()

    assert result.returncode == 0
    assert "OPENROUTER_FREE_ONLY" not in captured
    assert "OPENROUTER_API_KEY" not in captured
    assert "PYTHONPATH" not in captured


def test_refuses_non_forward_update(tmp_path):
    root = make_install(tmp_path, "ALICE v3.10")
    payload = make_payload(tmp_path, "ALICE v3.9")
    updater = InPlaceUpdater(root)
    with pytest.raises(UpgradeError, match="non-forward"):
        updater.apply(payload)


def test_manifest_tamper_rejected(tmp_path):
    root = make_install(tmp_path)
    payload = make_payload(tmp_path)
    m = build_manifest(payload, "ALICE v3.10", "ALICE v3.9")
    (payload / "upgrade_manifest.json").write_text(json.dumps(m), encoding="utf-8")
    (payload / "alice" / "marker.py").write_text("VALUE='tampered'\n", encoding="utf-8")
    with pytest.raises(UpgradeError, match="Hash mismatch"):
        InPlaceUpdater(root).validate_package(payload)


def test_package_cannot_touch_protected_state(tmp_path):
    root = make_install(tmp_path)
    payload = tmp_path / "payload"
    (payload / "alice_workspace").mkdir(parents=True)
    (payload / "alice_workspace" / "evil.json").write_text("{}", encoding="utf-8")
    (payload / "VERSION.txt").write_text("ALICE v3.10\n", encoding="utf-8")
    m = {
        "format": 1, "product": "ALICE", "version": "ALICE v3.10", "base_version": "ALICE v3.9",
        "files": [{"path": "alice_workspace/evil.json", "sha256": "0" * 64, "size": 2}], "deletions": []
    }
    (payload / "upgrade_manifest.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(UpgradeError, match="protected"):
        InPlaceUpdater(root).validate_package(payload)
