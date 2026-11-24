from alice.capabilities.manager import CapabilityManager
from alice.self_model import SelfModelSnapshot

def test_snapshot_distinguishes_verified_and_unverified(tmp_path):
    m=CapabilityManager(tmp_path); m.register("demo", "demo"); m.record_success("demo"); m.register("future", "future")
    s=SelfModelSnapshot.build(m); assert "demo" in s.available and "future" in s.unverified and s.verified_count >= 1

def test_snapshot_reports_degraded_as_gap(tmp_path):
    m=CapabilityManager(tmp_path); m.register("demo", "demo"); m.record_failure("demo", "timeout")
    s=SelfModelSnapshot.build(m); assert "demo" in s.degraded and s.capability_gap("demo")["gap"] is True

def test_snapshot_is_advisory_and_machine_readable(tmp_path):
    s=SelfModelSnapshot.build(CapabilityManager(tmp_path)); data=s.to_dict(); assert isinstance(data["available"], list) and "generated_at" in data
