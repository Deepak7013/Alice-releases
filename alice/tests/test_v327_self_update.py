import json, zipfile
from pathlib import Path
import pytest


def test_update_service_requires_verified_https_source(tmp_path):
    from alice.deployment.update_service import UpdateService
    u=UpdateService(tmp_path)
    r=u.configure(feed_url="https://updates.example/alice.json", auto_check=True, auto_install=False)
    assert r["feed_url"].startswith("https://")
    assert r["auto_check"] is True
    assert r["auto_install"] is False


def test_update_service_rejects_unverified_feed(monkeypatch, tmp_path):
    from alice.deployment.update_service import UpdateService, UpgradeError
    u=UpdateService(tmp_path)
    u.configure(feed_url="https://updates.example/alice.json")
    monkeypatch.setattr(u, "_get_json", lambda url: {"product":"ALICE","version":"ALICE v3.28","package_url":"https://updates.example/a.zip"})
    try:
        u.check()
        assert False, "missing digest must be rejected"
    except UpgradeError as exc:
        assert "signed manifest and signature" in str(exc).lower()


def test_update_service_rejects_digest_only_release(monkeypatch, tmp_path):
    from alice.deployment.update_service import UpdateService
    from alice.deployment.updater import UpgradeError
    (tmp_path/"VERSION.txt").write_text("ALICE v3.27\n",encoding="utf-8")
    u=UpdateService(tmp_path)
    u.configure(feed_url="https://updates.example/alice.json")
    monkeypatch.setattr(u, "_get_json", lambda url: {"product":"ALICE","version":"ALICE v3.28","package_url":"https://updates.example/a.zip","sha256":"a"*64})
    with pytest.raises(UpgradeError,match="signed manifest and signature"):
        u.check()


def test_updater_accepts_full_zip_package(tmp_path):
    from alice.deployment.updater import InPlaceUpdater, build_manifest
    payload=tmp_path/"payload"; payload.mkdir(); (payload/"VERSION.txt").write_text("ALICE v3.28\n",encoding="utf-8")
    (payload/"alice").mkdir(); (payload/"alice"/"x.py").write_text("x=1\n",encoding="utf-8")
    (payload/"upgrade_manifest.json").write_text(json.dumps(build_manifest(payload,"ALICE v3.28","ALICE v3.27")),encoding="utf-8")
    z=tmp_path/"update.zip"
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as f:
        for p in payload.rglob("*"):
            if p.is_file(): f.write(p,p.relative_to(payload).as_posix())
    root=tmp_path/"root"; (root/"alice").mkdir(parents=True); (root/"VERSION.txt").write_text("ALICE v3.27\n",encoding="utf-8"); (root/".venv"/"Scripts").mkdir(parents=True); (root/".venv"/"Scripts"/"python.exe").write_bytes(b"fake")
    result=InPlaceUpdater(root).validate_package(z)
    assert result["manifest"]["version"]=="ALICE v3.28"
