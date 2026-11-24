from pathlib import Path
import json, zipfile
from alice.deployment.updater import InPlaceUpdater, UpgradeError
from alice.deployment.update_service import UpdateService

def test_local_zip_update_center_and_service_are_wired():
    text=Path(__file__).parents[1].joinpath("ui","app.py").read_text(encoding="utf-8")
    assert "Browse ZIP..." in text
    assert "Install ZIP" in text
    assert "check_local" in text

def test_zip_traversal_is_rejected(tmp_path):
    z=tmp_path/"bad.zip"
    with zipfile.ZipFile(z,"w") as f:
        f.writestr("../evil.txt","bad")
    u=InPlaceUpdater(tmp_path)
    try:
        u._safe_extract_zip(z,tmp_path/"stage")
    except UpgradeError:
        return
    assert False, "path traversal ZIP was accepted"

def test_update_service_exposes_local_zip_state(tmp_path):
    (tmp_path/"alice_workspace"/"runtime").mkdir(parents=True)
    (tmp_path/"VERSION.txt").write_text("ALICE v3.33.0\n",encoding="utf-8")
    svc=UpdateService(tmp_path)
    st=svc.status()
    assert "local_zip" in st and "auto_install_local" in st
