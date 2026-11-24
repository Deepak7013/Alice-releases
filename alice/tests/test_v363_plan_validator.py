from alice.capabilities.manager import CapabilityManager
from alice.executive.plan_validator import ExecutivePlanValidator

def test_empty_plan_is_invalid(tmp_path):
    assert not ExecutivePlanValidator(CapabilityManager(tmp_path)).validate([]).valid

def test_unready_capability_blocks_plan(tmp_path):
    m=CapabilityManager(tmp_path); m.register("printer", "printer")
    v=ExecutivePlanValidator(m).validate([{"description":"print report", "capability":"printer"}])
    assert not v.valid and "printer" in v.reason

def test_verified_plan_requires_completion_evidence(tmp_path):
    m=CapabilityManager(tmp_path); m.register("demo", "demo"); m.record_success("demo")
    v=ExecutivePlanValidator(m).validate([{"description":"run demo", "capability":"demo", "side_effect":True}])
    assert v.valid and v.requires_verification
    assert not ExecutivePlanValidator.completion_claim_allowed(v, {"ok":False})
    assert ExecutivePlanValidator.completion_claim_allowed(v, {"ok":True})
