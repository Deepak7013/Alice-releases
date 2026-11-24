import json
from pathlib import Path
from alice.deployment.installer_verify import verify, write_manifest


def test_installer_manifest_matches_current_tree():
    root = Path(__file__).resolve().parents[2]
    result = verify(root)
    assert result["ok"], result


def test_installer_verifier_detects_tampering(tmp_path):
    (tmp_path / "full_install_manifest.json").write_text(json.dumps({
        "format": 1, "product": "ALICE", "version": "ALICE v3.54.0",
        "files": [{"path": "hello.txt", "sha256": "bad", "size": 1}]
    }), encoding="utf-8")
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    result = verify(tmp_path)
    assert not result["ok"]
    assert "hello.txt" in result["mismatched"]



def test_installer_verifier_ignores_runtime_migration_artifacts(tmp_path):
    # Simulate a small immutable package plus protected data copied from an
    # existing Windows installation after staging. Runtime artifacts must not
    # invalidate the immutable release manifest.
    payload = tmp_path / "payload.txt"
    payload.write_text("release payload", encoding="utf-8")
    import hashlib
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    (tmp_path / "full_install_manifest.json").write_text(json.dumps({
        "format": 1, "product": "ALICE", "version": "ALICE v3.100.0",
        "files": [{"path": "payload.txt", "sha256": digest, "size": payload.stat().st_size}]
    }), encoding="utf-8")
    (tmp_path / "data" / "workspace").mkdir(parents=True)
    (tmp_path / "data" / "workspace" / "alice_screen.png").write_bytes(b"runtime-screen")
    (tmp_path / "ALICE_INSTALL.log").write_text("runtime log", encoding="utf-8")
    result = verify(tmp_path)
    assert result["ok"], result


def test_full_install_manifest_ignores_update_control_manifest(tmp_path):
    import hashlib
    payload = tmp_path / "payload.txt"
    payload.write_text("payload", encoding="utf-8")
    (tmp_path / "full_install_manifest.json").write_text(json.dumps({
        "format": 1, "product": "ALICE", "version": "ALICE v4.108.1",
        "files": [{"path": "payload.txt", "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(), "size": payload.stat().st_size}]
    }), encoding="utf-8")
    (tmp_path / "upgrade_manifest.json").write_text("per-update metadata", encoding="utf-8")

    result = verify(tmp_path)

    assert result["ok"] is True, result


def test_manifest_writer_hashes_the_current_full_installer_tree(tmp_path):
    (tmp_path / "VERSION.txt").write_text("ALICE v4.104.0\n", encoding="utf-8")
    (tmp_path / "alice.py").write_text("VALUE = 1\n", encoding="utf-8")

    result = write_manifest(tmp_path)

    assert result["ok"] is True
    assert result["version"] == "ALICE v4.104.0"
    assert result["manifest_files"] == 2
    assert verify(tmp_path)["ok"] is True


def test_installer_manifest_skips_named_development_virtual_environments(tmp_path):
    (tmp_path / "VERSION.txt").write_text("ALICE v4.104.0\n", encoding="utf-8")
    (tmp_path / "alice.py").write_text("VALUE = 1\n", encoding="utf-8")
    development_env = tmp_path / ".venv-c43" / "Lib" / "site-packages"
    development_env.mkdir(parents=True)
    (development_env / "large-development-only.bin").write_bytes(b"local venv")

    manifest = write_manifest(tmp_path)

    assert manifest["ok"] is True
    assert manifest["manifest_files"] == 2
    assert ".venv-c43/Lib/site-packages/large-development-only.bin" not in {
        row["path"] for row in json.loads((tmp_path / "full_install_manifest.json").read_text())["files"]
    }
