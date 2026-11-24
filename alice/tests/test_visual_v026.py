
from alice.vision.models import VisualFrame, VisualObservation, VisualTarget
from alice.vision.adapter import VisionAdapter
from alice.vision.loop import VisualActionLoop
from alice.computer.models import ActionResult

class FakeController:
    platform = "windows"
    def __init__(self):
        self.state = 0
        self.clicks = 0
    def observe(self):
        from alice.computer.models import ScreenState
        return ScreenState("windows", fingerprint=str(self.state))
    def click(self, x, y):
        self.clicks += 1
        if self.clicks >= 2:
            self.state += 1
        return ActionResult(True, "click", "ok", True)

class FakeVision(VisionAdapter):
    def analyze(self, frame, goal):
        target = VisualTarget("Login", "button", 0.99, (10, 20, 100, 40))
        return VisualObservation(frame, [target], "Login", 0.99)

def test_visual_click_verified():
    c = FakeController()
    loop = VisualActionLoop(c, FakeVision(), max_recovery_attempts=2)
    r = loop.click_target("log in", "Login", "button")
    assert r["ok"] and r["verified"]
    assert c.clicks == 2

class EmptyVision(VisionAdapter):
    def analyze(self, frame, goal):
        return VisualObservation(frame, [], "", 0.0)

def test_missing_target_is_bounded():
    c = FakeController()
    loop = VisualActionLoop(c, EmptyVision(), max_recovery_attempts=2)
    r = loop.click_target("log in", "Login", "button")
    assert not r["ok"]
    assert r["attempts"] == 3
