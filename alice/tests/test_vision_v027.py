
from alice.vision.models import VisualFrame, VisualObservation, VisualTarget
from alice.vision.providers import VisionRouter, VisionProvider, VisionProviderResult
from alice.vision.hierarchy import HierarchyNode, UIHierarchyAdapter
from alice.vision.fusion import EvidenceFusion

class Bad(VisionProvider):
    name = "bad"
    def analyze(self, image, prompt):
        return VisionProviderResult(False, error="failed")

class Good(VisionProvider):
    name = "good"
    def analyze(self, image, prompt):
        return VisionProviderResult(True, text="login detected")

def test_provider_fallback():
    r = VisionRouter([Bad(), Good()])
    result = r.analyze(None, "find login")
    assert result.ok and result.provider == "good"

def test_hierarchy_normalization():
    root = HierarchyNode("window", "App", children=[
        HierarchyNode("button", "Login", (1,2,30,20))
    ])
    targets = UIHierarchyAdapter().targets(root)
    assert any(t.name == "Login" and t.role == "button" for t in targets)

def test_native_wins_duplicate():
    frame = VisualFrame("windows", fingerprint="x")
    vision = VisualObservation(frame, [
        VisualTarget("Login", "button", 0.60, (99,99,20,20)),
        VisualTarget("Help", "button", 0.90, (50,50,20,20))
    ], "", 0.9)
    hierarchy = HierarchyNode("window", "App", children=[
        HierarchyNode("button", "Login", (1,2,30,20))
    ])
    merged = EvidenceFusion().merge(vision, hierarchy)
    login = [t for t in merged.targets if t.name == "Login"]
    assert len(login) == 1
    assert login[0].bounds == (1,2,30,20)
    assert any(t.name == "Help" for t in merged.targets)
