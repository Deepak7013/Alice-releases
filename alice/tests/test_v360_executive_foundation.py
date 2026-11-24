from alice.executive import ExecutiveFoundation
from alice.capabilities.manager import CapabilityManager

def test_hypothetical_never_becomes_executable(tmp_path):
    e=ExecutiveFoundation(root=tmp_path)
    d=e.prepare("Suppose I delete a file. Do not execute.")
    assert d.executable is False and d.approval_required is False

def test_action_creates_workspace_and_requires_approval(tmp_path):
    e=ExecutiveFoundation(root=tmp_path)
    d=e.prepare("run the build", mode="debug")
    assert d.workspace_id and d.executable and d.approval_required

def test_unverified_capability_blocks_executability(tmp_path):
    m=CapabilityManager(tmp_path); m.register("android_control", "control phone")
    e=ExecutiveFoundation(root=tmp_path, capabilities=m)
    d=e.prepare("open the phone", capability="android_control")
    assert d.capability_gap["gap"] is True and d.executable is False

def test_verified_capability_allows_routing(tmp_path):
    m=CapabilityManager(tmp_path); m.register("demo", "demo"); m.record_success("demo")
    e=ExecutiveFoundation(root=tmp_path, capabilities=m)
    d=e.prepare("run the demo", capability="demo")
    assert d.executable is True

def test_completion_requires_positive_evidence():
    assert ExecutiveFoundation.completion_ready({"ok": True})
    assert not ExecutiveFoundation.completion_ready({"ok": False})
    assert not ExecutiveFoundation.completion_ready(None)
