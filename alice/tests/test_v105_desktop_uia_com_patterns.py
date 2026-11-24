from __future__ import annotations

import hashlib

from alice.computer.uia import WindowsUIAutomation


class _Array:
    def __init__(self, elements):
        self.elements = elements
        self.Length = len(elements)

    def GetElement(self, index):
        return self.elements[index]


class _ValuePattern:
    CurrentValue = "private composer text"


class _UnknownPointer:
    def __init__(self, pattern):
        self.pattern = pattern
        self.queried_interface = None

    def QueryInterface(self, interface):
        self.queried_interface = interface
        return self.pattern


class _Rect:
    def __init__(self, left=10, top=20, right=31, bottom=41):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class _Element:
    def __init__(self, name="Provider", control_type=50000, runtime_id=(15,), rect=None):
        self.CurrentName = name
        self.CurrentControlType = control_type
        self.CurrentIsEnabled = True
        self.CurrentIsOffscreen = False
        self.CurrentIsPassword = False
        self.CurrentHasKeyboardFocus = False
        self.CurrentBoundingRectangle = rect or _Rect()
        self.runtime_id = list(runtime_id)
        self.pointer = _UnknownPointer(_ValuePattern())

    def GetRuntimeId(self):
        return self.runtime_id

    def GetCurrentPattern(self, _pattern_id):
        return self.pointer


class _Window:
    CurrentNativeWindowHandle = 123

    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.read_count = 0

    def FindAll(self, _scope, _condition):
        index = min(self.read_count, len(self.snapshots) - 1)
        self.read_count += 1
        return _Array(self.snapshots[index])


class _Automation:
    @staticmethod
    def CreateTrueCondition():
        return object()


class _Comtypes:
    @staticmethod
    def CoUninitialize():
        pass


class _Module:
    TreeScope_Subtree = 7
    UIA_ValuePatternId = 10002
    UIA_TextPatternId = 10014
    IUIAutomationValuePattern = object()
    IUIAutomationTextPattern = object()


class _Controller:
    def __init__(self, foreground=(True, True)):
        self.foreground = list(foreground)
        self.clicked = []

    @staticmethod
    def screen_size():
        return {"width": 100, "height": 100}

    def is_foreground_window(self, hwnd):
        assert hwnd == 123
        return self.foreground.pop(0) if len(self.foreground) > 1 else self.foreground[0]

    def click(self, x, y):
        self.clicked.append((x, y))


def _observer(snapshots, controller=None):
    observer = WindowsUIAutomation(controller=controller or _Controller())
    observer._connect = lambda: (_Comtypes, _Module, _Automation(), _Window(snapshots))
    return observer


def test_focused_edit_fingerprint_queries_generic_pointer_for_value_interface():
    edit = _Element(name="", control_type=50004)
    edit.CurrentHasKeyboardFocus = True
    observer = _observer([[edit]])

    result = observer.focused_edit_value_fingerprint()

    assert result["ok"] is True
    assert edit.pointer.queried_interface is _Module.IUIAutomationValuePattern
    assert result["value_length"] == len(_ValuePattern.CurrentValue)
    assert result["value_sha256"] == hashlib.sha256(_ValuePattern.CurrentValue.encode()).hexdigest()
    assert _ValuePattern.CurrentValue not in str(result)


def test_accessible_click_uses_fresh_exact_bounds_and_controller():
    target = _Element()
    controller = _Controller()
    observer = _observer([[target], [target]], controller)

    result = observer.click_exact("Provider", "Configure ALICE AI Provider")

    assert result["ok"] is True
    assert result["action"] == "desktop_click_accessible"
    assert result["target_sha256"] == hashlib.sha256(b"provider").hexdigest()
    assert controller.clicked == [(20, 30)]


def test_accessible_click_fails_closed_when_expected_text_arrives_before_click():
    target = _Element()
    observed_text = _Element(name="Configure ALICE AI Provider", control_type=50020)
    controller = _Controller()
    observer = _observer([[target], [target, observed_text]], controller)

    result = observer.click_exact("Provider", "Configure ALICE AI Provider")

    assert result["ok"] is False
    assert result["error"] == "expected_text_already_visible"
    assert controller.clicked == []


def test_accessible_click_fails_closed_when_target_identity_or_bounds_change():
    original = _Element(runtime_id=(15,))
    moved = _Element(runtime_id=(16,), rect=_Rect(60, 60, 80, 80))
    controller = _Controller()
    observer = _observer([[original], [moved]], controller)

    result = observer.click_exact("Provider", "Configure ALICE AI Provider")

    assert result["ok"] is False
    assert result["error"] == "accessibility_target_stale"
    assert controller.clicked == []


def test_accessible_click_fails_closed_if_foreground_changes():
    target = _Element()
    controller = _Controller(foreground=(True, False))
    observer = _observer([[target], [target]], controller)

    result = observer.click_exact("Provider", "Configure ALICE AI Provider")

    assert result["ok"] is False
    assert result["error"] == "foreground_window_changed"
    assert controller.clicked == []
