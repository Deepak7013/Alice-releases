
from pathlib import Path
import json
from alice.maintenance.self_manager import SelfManager

class FakeRouter:
    def __init__(self, payloads):
        self.payloads = list(payloads)
    def ask(self, prompt, image_path=None):
        return self.payloads.pop(0)

def test_candidate_failure_does_not_touch_live_source(tmp_path):
    root = tmp_path / "alice_app"
    (root / "alice").mkdir(parents=True)
    target = root / "alice" / "feature.py"
    target.write_text("VALUE = 1\n")
    lab = SelfManager(root)
    lab.run_tests = lambda cwd=None: type("R", (), {"returncode": 1, "stdout": "", "stderr": "fail"})()
    result = lab.apply_patch([{"path":"alice/feature.py","content":"VALUE = 2\n"}])
    assert not result["ok"]
    assert not result["promoted"]
    assert target.read_text() == "VALUE = 1\n"

def test_successful_candidate_is_promoted(tmp_path):
    root = tmp_path / "alice_app"
    (root / "alice").mkdir(parents=True)
    target = root / "alice" / "feature.py"
    target.write_text("VALUE = 1\n")
    lab = SelfManager(root)
    lab.run_tests = lambda cwd=None: type("R", (), {"returncode": 0, "stdout": "2 passed", "stderr": ""})()
    result = lab.apply_patch([{"path":"alice/feature.py","content":"VALUE = 2\n"}])
    assert result["ok"] and result["promoted"]
    assert target.read_text() == "VALUE = 2\n"

def test_protected_security_tree_cannot_be_changed(tmp_path):
    root = tmp_path / "alice_app"
    (root / "alice" / "security").mkdir(parents=True)
    (root / "alice" / "security" / "policy.py").write_text("SAFE=True\n")
    lab = SelfManager(root)
    try:
        lab.apply_patch([{"path":"alice/security/policy.py","content":"SAFE=False\n"}])
    except ValueError as exc:
        assert "protected" in str(exc)
    else:
        assert False

def test_self_upgrade_uses_verified_patch_pipeline(tmp_path):
    root = tmp_path / "alice_app"
    (root / "alice").mkdir(parents=True)
    target = root / "alice" / "feature.py"
    target.write_text("VALUE = 1\n")
    selection = json.dumps({"reason":"add requested capability","files":["alice/feature.py"]})
    payload = json.dumps({
        "reason":"add requested capability",
        "changes":[{"path":"alice/feature.py","content":"VALUE = 2\n"}]
    })
    lab = SelfManager(root, router=FakeRouter([selection, payload]))
    lab.run_tests = lambda cwd=None: type("R", (), {"returncode": 0, "stdout": "all passed", "stderr": ""})()
    result = lab.self_upgrade("add the capability")
    assert result["ok"] and result["promoted"]
    assert target.read_text() == "VALUE = 2\n"
