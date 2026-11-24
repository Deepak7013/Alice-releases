import base64
import copy
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from alice.deployment.signed_updates import (
    SignedUpdateVerifier,
    UpdateJournal,
    canonical_manifest_bytes,
    create_signed_update_envelope,
    enroll_trusted_key,
    strict_json_loads,
    verify_signed_package,
)
from alice.deployment.update_service import UpdateService
from alice.deployment.updater import UpgradeError, build_manifest


def _signed_fixture(tmp_path, *, trusted=True, channel="stable", platform_name="any"):
    root = tmp_path / "install"
    root.mkdir()
    (root / "VERSION.txt").write_text("ALICE v4.106.0\n", encoding="utf-8")
    (root / "alice").mkdir()
    (root / ".venv" / "Scripts").mkdir(parents=True)
    (root / ".venv" / "Scripts" / "python.exe").write_bytes(b"test interpreter")

    payload = tmp_path / "payload"
    (payload / "alice").mkdir(parents=True)
    (payload / "VERSION.txt").write_text("ALICE v4.107.0\n", encoding="utf-8")
    (payload / "alice" / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    package_manifest = build_manifest(payload, "ALICE v4.107.0", "ALICE v4.106.0")
    (payload / "upgrade_manifest.json").write_text(json.dumps(package_manifest), encoding="utf-8")
    package_path = tmp_path / "ALICE_v4.107.0.zip"
    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(payload).as_posix())

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = hashlib.sha256(public).hexdigest()
    if trusted:
        enroll_trusted_key(root, public, key_id)
    rows = [{"path": row["path"], "sha256": row["sha256"], "size": row["size"]} for row in package_manifest["files"]]
    signed_manifest = {
        "schema": 1,
        "product": "ALICE",
        "channel": channel,
        "version": "ALICE v4.107.0",
        "sequence": 107,
        "platform": platform_name,
        "minimum_os": "any",
        "minimum_runtime": "3.14.0",
        "minimum_supported_version": "ALICE v4.100.0",
        "package": {"url": "https://updates.example/ALICE_v4.107.0.zip", "sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(), "size": package_path.stat().st_size},
        "files": rows,
        "release_notes": "Cycle 2 signed test update",
        "migrations": [],
        "key_id": key_id,
    }
    envelope = {"manifest": signed_manifest, "signature": base64.b64encode(private.sign(canonical_manifest_bytes(signed_manifest))).decode("ascii")}
    sidecar = Path(str(package_path) + ".update.json")
    sidecar.write_text(json.dumps(envelope), encoding="utf-8")
    return root, package_path, sidecar, envelope, private


def _resign(envelope, private):
    envelope["signature"] = base64.b64encode(private.sign(canonical_manifest_bytes(envelope["manifest"]))).decode("ascii")
    return envelope


def test_signed_package_passes_pinned_signature_hash_and_inventory(tmp_path):
    root, package, sidecar, _envelope, _private = _signed_fixture(tmp_path)
    result = verify_signed_package(root, package, sidecar)
    assert result["ok"] is True
    assert result["manifest"]["sequence"] == 107
    assert result["file_count"] == 2


def test_publisher_signing_flow_emits_verifiable_detached_manifest(tmp_path):
    root, package, sidecar, _old_envelope, private = _signed_fixture(tmp_path)
    envelope = create_signed_update_envelope(
        package, private,
        package_url="https://updates.example/ALICE_v4.107.0.zip",
        channel="stable", sequence=107, platform_name="any", minimum_os="any",
        minimum_runtime="3.14.0", minimum_supported_version="ALICE v4.100.0",
        release_notes="Publisher tool test",
    )
    sidecar.write_text(json.dumps(envelope), encoding="utf-8")
    assert verify_signed_package(root, package, sidecar)["manifest"]["sequence"] == 107


def test_unsigned_local_package_and_unknown_key_fail_closed(tmp_path):
    root, package, sidecar, _envelope, _private = _signed_fixture(tmp_path, trusted=False)
    with pytest.raises(UpgradeError, match="not trusted"):
        verify_signed_package(root, package, sidecar)
    sidecar.unlink()
    with pytest.raises(UpgradeError, match="sidecar is missing"):
        UpdateService(root).check_local(package)


def test_invalid_signature_tampering_channel_and_platform_are_rejected(tmp_path):
    root, package, sidecar, envelope, private = _signed_fixture(tmp_path)
    changed = copy.deepcopy(envelope)
    changed["signature"] = base64.b64encode(b"0" * 64).decode("ascii")
    sidecar.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(UpgradeError, match="signature verification failed"):
        verify_signed_package(root, package, sidecar)

    for field, value, error in (("channel", "beta", "channel"), ("platform", "linux-amd64", "does not support")):
        changed = copy.deepcopy(envelope)
        changed["manifest"][field] = value
        _resign(changed, private)
        sidecar.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(UpgradeError, match=error):
            verify_signed_package(root, package, sidecar)

    changed = copy.deepcopy(envelope)
    changed["manifest"]["release_notes"] = "modified"
    sidecar.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(UpgradeError, match="signature verification failed"):
        verify_signed_package(root, package, sidecar)

    sidecar.write_text(json.dumps(envelope), encoding="utf-8")
    with package.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(UpgradeError, match="size or SHA-256"):
        verify_signed_package(root, package, sidecar)


@pytest.mark.parametrize("bad_path", ["../escape.py", "/absolute.py", "C:/drive.py", "//server/share.py", "alice\\evil.py", "CON", "NUL.txt", "folder/trailing."])
def test_signed_manifest_rejects_unsafe_paths(tmp_path, bad_path):
    root, package, sidecar, envelope, private = _signed_fixture(tmp_path)
    changed = copy.deepcopy(envelope)
    changed["manifest"]["files"][0]["path"] = bad_path
    _resign(changed, private)
    sidecar.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(UpgradeError, match="path"):
        verify_signed_package(root, package, sidecar)


def test_duplicate_json_unknown_fields_oversize_and_sequence_replay_fail(tmp_path):
    with pytest.raises(UpgradeError, match="Duplicate JSON key"):
        strict_json_loads('{"manifest":{},"manifest":{}}')
    root, package, sidecar, envelope, private = _signed_fixture(tmp_path)
    changed = copy.deepcopy(envelope)
    changed["critical_extra"] = "must not be ignored"
    sidecar.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(UpgradeError, match="only a signed manifest"):
        verify_signed_package(root, package, sidecar)
    changed = copy.deepcopy(envelope)
    changed["manifest"]["package"]["size"] = 600 * 1024 * 1024
    _resign(changed, private)
    sidecar.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(UpgradeError, match="size limit"):
        verify_signed_package(root, package, sidecar)
    sidecar.write_text(json.dumps(envelope), encoding="utf-8")
    SignedUpdateVerifier(root).record_success(107, "ALICE v4.107.0")
    with pytest.raises(UpgradeError, match="replay or downgrade") as exc:
        verify_signed_package(root, package, sidecar)
    assert "package sequence 107" in str(exc.value)
    assert "highest accepted sequence 107" in str(exc.value)
    assert "ALICE v4.107.0" in str(exc.value)


def test_signed_feed_check_and_download_stage_verified_zip(monkeypatch, tmp_path):
    root, package, _sidecar, envelope, _private = _signed_fixture(tmp_path)
    svc = UpdateService(root)
    svc.configure(feed_url="https://updates.example/feed.json")
    monkeypatch.setattr(svc, "_get_json", lambda _url: envelope)
    payload = package.read_bytes()

    class FakeResponse:
        headers = {"Content-Length": str(len(payload))}

        def __init__(self):
            from io import BytesIO
            self.stream = BytesIO(payload)

        def __enter__(self): return self
        def __exit__(self, *_args): self.stream.close()
        def geturl(self): return "https://updates.example/ALICE_v4.107.0.zip"
        def read(self, size=-1): return self.stream.read(size)

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse())
    checked = svc.check()
    assert checked["signed"] is True and checked["available"] is True
    downloaded = svc.download(checked)
    assert downloaded["downloaded"] is True
    assert Path(downloaded["package"]).is_file()
    assert Path(downloaded["sidecar"]).is_file()
    assert verify_signed_package(root, downloaded["package"], downloaded["sidecar"])["ok"] is True


def test_external_update_entrypoints_reverify_signed_sidecar():
    source = Path(__file__).parents[1]
    app = (source / "ui" / "app.py").read_text(encoding="utf-8")
    helper = (source / "deployment" / "update_helper.py").read_text(encoding="utf-8")
    assert "check = verify_signed_package(updater.root, package)" in app
    assert "check=verify_signed_package(root,package)" in app
    assert "verified = verify_signed_package(root, package)" in helper
    assert "record_signed_update_success(root, signed_manifest)" in helper


def test_interrupted_apply_rolls_back_from_journal(tmp_path):
    from alice.deployment.updater import InPlaceUpdater

    root = tmp_path / "install"
    (root / "alice").mkdir(parents=True)
    (root / "VERSION.txt").write_text("ALICE v4.106.0\n", encoding="utf-8")
    target = root / "alice" / "existing.py"
    target.write_text("before\n", encoding="utf-8")
    updater = InPlaceUpdater(root)
    backup = updater._backup_path()
    updater._backup_existing(["alice/existing.py"], backup)
    target.write_text("partially applied\n", encoding="utf-8")
    journal = UpdateJournal(root)
    journal.transition("APPLYING", version="ALICE v4.107.0", sequence=107,
                       package_sha256="a" * 64, backup=str(backup))

    result = UpdateService(root).recover_interrupted()
    assert result["state"] == "ROLLED_BACK"
    assert target.read_text(encoding="utf-8") == "before\n"


def test_rollback_refuses_tampered_backup_path_escape(tmp_path):
    from alice.deployment.updater import InPlaceUpdater

    root = tmp_path / "install"
    (root / "alice").mkdir(parents=True)
    (root / "VERSION.txt").write_text("ALICE v4.106.0\n", encoding="utf-8")
    updater = InPlaceUpdater(root)
    backup = updater._backup_path()
    (backup / "backup.json").write_text(json.dumps({"root": str(root), "files": ["../outside.txt"], "created": []}), encoding="utf-8")
    with pytest.raises(UpgradeError, match="Unsafe rollback backup path"):
        updater.rollback(backup)


def test_update_state_journal_fails_closed_when_corrupt(tmp_path):
    root = tmp_path / "install"
    (root / "alice_workspace" / "runtime").mkdir(parents=True)
    (root / "alice_workspace" / "runtime" / "update_state_machine.json").write_text('{"schema":1,"state":"MAGIC"}', encoding="utf-8")
    with pytest.raises(UpgradeError, match="journal is corrupt"):
        UpdateJournal(root).read()


def test_active_updater_blocks_second_alice_process_but_allows_its_health_child(monkeypatch, tmp_path):
    root = tmp_path / "install"
    (root / "alice").mkdir(parents=True)
    (root / "VERSION.txt").write_text("ALICE v4.106.0\n", encoding="utf-8")
    service = UpdateService(root)
    monkeypatch.setattr(service, "_pid_is_running", lambda _pid: True)
    UpdateJournal(root).transition("APPLYING", helper_pid=4040, backup=str(root / ".alice_backups"))
    monkeypatch.setattr("os.getppid", lambda: 5050)
    assert service.startup_allowed() is False
    UpdateJournal(root).transition("HEALTH_CHECK", helper_pid=5050)
    assert service.startup_allowed() is True


def test_update_helper_does_not_treat_old_process_timeout_as_exit(monkeypatch):
    import sys
    import types
    from alice.deployment import update_helper

    monkeypatch.setitem(sys.modules, "psutil", types.SimpleNamespace(pid_exists=lambda _pid: True))
    monkeypatch.setattr(update_helper.time, "sleep", lambda _seconds: None)
    assert update_helper._wait_for_pid_exit(31415) is False


@pytest.mark.parametrize("test_exit,expected_ok", [(0, True), (1, False)])
def test_signed_update_apply_or_test_failure_rollback_preserves_protected_data(monkeypatch, tmp_path, test_exit, expected_ok):
    from alice.deployment.updater import InPlaceUpdater

    root, package, sidecar, _envelope, _private = _signed_fixture(tmp_path)
    (root / ".env").write_text("ALICE_TEST_SECRET=preserve-me\n", encoding="utf-8")
    signed = verify_signed_package(root, package, sidecar)
    updater = InPlaceUpdater(root)
    monkeypatch.setattr(updater, "_run_tests", lambda: subprocess.CompletedProcess(["pytest"], test_exit, "fixture tests", ""))
    states = []
    result = updater.apply(package, expected_sha256=signed["manifest"]["package"]["sha256"],
                          state_callback=lambda state, backup: states.append((state, str(backup))))
    assert result["ok"] is expected_ok
    assert (root / ".env").read_text(encoding="utf-8") == "ALICE_TEST_SECRET=preserve-me\n"
    if expected_ok:
        assert (root / "alice" / "feature.py").read_text(encoding="utf-8") == "VALUE = 1\n"
        assert states == [("BACKED_UP", result["backup"]), ("APPLYING", result["backup"])]
    else:
        assert result["rolled_back"] is True
        assert not (root / "alice" / "feature.py").exists()
