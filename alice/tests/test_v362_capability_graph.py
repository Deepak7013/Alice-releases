from alice.capabilities.manager import CapabilityManager
from alice.self_model.capability_graph import CapabilityGraph

def test_dependency_must_be_verified(tmp_path):
    m=CapabilityManager(tmp_path)
    m.register("browser_driver", "driver")
    m.register("browser_automation", "browser", dependencies=["browser_driver"])
    m.record_success("browser_automation")
    r=CapabilityGraph(m).readiness("browser_automation")
    assert not r.ready and "browser_driver" in r.degraded

def test_dependency_chain_can_be_ready(tmp_path):
    m=CapabilityManager(tmp_path)
    m.register("driver", "driver")
    m.register("browser", "browser", dependencies=["driver"])
    m.record_success("driver"); m.record_success("browser")
    r=CapabilityGraph(m).readiness("browser")
    assert r.ready and r.reason == "ready"

def test_unknown_dependency_is_reported(tmp_path):
    m=CapabilityManager(tmp_path)
    m.register("phone", "phone", dependencies=["bridge"])
    m.record_success("phone")
    r=CapabilityGraph(m).readiness("phone")
    assert not r.ready and "bridge" in r.missing
