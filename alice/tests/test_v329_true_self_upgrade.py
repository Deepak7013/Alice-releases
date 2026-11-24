from pathlib import Path
import json, zipfile
from alice.maintenance.self_manager import SelfManager
from alice.deployment.updater import InPlaceUpdater

class FakeRouter:
    def __init__(self, payloads): self.payloads=list(payloads)
    def ask(self, prompt, image_path=None): return self.payloads.pop(0)

def passed():
    return type("R", (), {"returncode":0,"stdout":"397 passed","stderr":""})()

def test_self_engineer_builds_verified_forward_package(tmp_path):
    root=tmp_path/"alice_app"
    (root/"alice").mkdir(parents=True)
    (root/"alice"/"feature.py").write_text("VALUE=1\n", encoding="utf-8")
    (root/"VERSION.txt").write_text("ALICE v3.29.0\n", encoding="utf-8")
    selection=json.dumps({"reason":"add feature","files":["alice/feature.py"]})
    implementation=json.dumps({"reason":"implemented","changes":[{"path":"alice/feature.py","content":"VALUE=2\n"}]})
    sm=SelfManager(root, router=FakeRouter([selection,implementation]))
    sm.diagnostics=lambda: {"ok":True,"python_files":1,"tests":"full_suite","errors":[]}
    sm.run_tests=lambda cwd=None: passed()
    result=sm.prepare_self_upgrade("add feature", repair_attempts=0)
    assert result["ok"] and result["status"]=="package_ready"
    assert result["target_version"]=="ALICE v3.29.1"
    assert result["changed"]==["alice/feature.py"]
    assert root.joinpath("alice/feature.py").read_text()=="VALUE=1\n"
    pkg=Path(result["package"])
    assert pkg.is_file()
    check=InPlaceUpdater(root).validate_package(pkg)
    assert check["manifest"]["self_generated"] is True
    with zipfile.ZipFile(pkg) as z:
        assert z.read("alice/feature.py").decode()=="VALUE=2\n"
        assert z.read("VERSION.txt").decode()=="ALICE v3.29.1\n"

def test_failed_candidate_never_produces_upgrade_package(tmp_path):
    root=tmp_path/"alice_app"; (root/"alice").mkdir(parents=True)
    (root/"alice"/"feature.py").write_text("VALUE=1\n")
    (root/"VERSION.txt").write_text("ALICE v3.29.0\n")
    selection=json.dumps({"reason":"bad change","files":["alice/feature.py"]})
    implementation=json.dumps({"reason":"bad","changes":[{"path":"alice/feature.py","content":"VALUE=broken\n"}]})
    sm=SelfManager(root, router=FakeRouter([selection,implementation]))
    sm.diagnostics=lambda: {"ok":True,"python_files":1,"tests":"full_suite","errors":[]}
    sm.run_tests=lambda cwd=None: type("R", (), {"returncode":1,"stdout":"","stderr":"candidate failure"})()
    result=sm.prepare_self_upgrade("bad change", repair_attempts=0)
    assert result["ok"] is False
    assert result["status"]=="candidate_failed"
    assert not list((root/"alice_workspace"/"updates").glob("*.zip")) if (root/"alice_workspace"/"updates").exists() else True
    assert (root/"alice"/"feature.py").read_text()=="VALUE=1\n"
