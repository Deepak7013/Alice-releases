
from alice.computer.models import UIElement, ScreenState
from alice.computer.session import ComputerSession
from alice.computer.windows import WindowsController
from alice.computer.android import AndroidController

class FakeWin:
    def __init__(self):
        self.clicked = []
        self.typed = []
    def observe(self):
        return ScreenState("windows", "Test", "Demo",
            [UIElement("1", "button", "Login", (10,20,100,40))], "abc")
    def click(self, e): self.clicked.append(e.name)
    def type_text(self, t): self.typed.append(t)

def test_semantic_click():
    b = FakeWin()
    s = ComputerSession(WindowsController(b))
    r = s.click("Login", "button")
    assert r.ok and b.clicked == ["Login"]

def test_missing_element_fails_cleanly():
    s = ComputerSession(WindowsController(FakeWin()))
    assert not s.click("Settings").ok

class FakeAdbResult:
    returncode = 0
    stdout = "List of devices attached\nABC123\tdevice\n"
    stderr = ""

class FakeAdb:
    def __init__(self): self.calls=[]
    def __call__(self, args):
        self.calls.append(args); return FakeAdbResult()

def test_android_device_and_tap():
    f = FakeAdb()
    a = AndroidController(runner=f)
    assert a.devices() == ["ABC123"]
    assert a.tap(100,200).ok
    assert ["shell","input","tap","100","200"] in f.calls
