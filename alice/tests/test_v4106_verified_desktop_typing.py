from alice.computer.verified_typing import (
    type_into_empty_focused_control,
    verify_desktop_typing,
)
from alice.computer.uia import WindowsUIAutomation


class FakeController:
    def __init__(self):
        self.typed = []

    def type_text(self, text):
        self.typed.append(text)


class FakeObserver:
    def __init__(self, states):
        self.states = list(states)

    def focused_edit_value_fingerprint(self):
        return self.states.pop(0)


def fp(value, focus="a" * 64):
    import hashlib
    return {"ok": True, "focus_sha256": focus,
            "value_sha256": hashlib.sha256(value.encode()).hexdigest(),
            "value_length": len(value)}


def test_verified_typing_accepts_empty_edit_and_verifies_exact_value_without_content():
    controller = FakeController()
    observer = FakeObserver([fp(""), fp("hello world")])
    result = type_into_empty_focused_control(controller, observer, "hello world")
    assert result["ok"] is True
    assert controller.typed == ["hello world"]
    check = verify_desktop_typing(observer, {"text": "hello world"}, result)
    assert check.ok is True
    assert check.evidence["expected_value_matches"] is True
    assert "hello world" not in repr(check.evidence)


def test_verified_typing_refuses_nonempty_edit_without_typing():
    controller = FakeController()
    result = type_into_empty_focused_control(controller, FakeObserver([fp("existing")]), "new")
    assert result["ok"] is False
    assert result["error"] == "focused_edit_control_not_empty"
    assert controller.typed == []


def test_verified_typing_refuses_password_or_unavailable_observation():
    controller = FakeController()
    for observation in ({"ok": False, "error": "password_control_forbidden"}, None):
        result = type_into_empty_focused_control(controller, FakeObserver([observation]), "secret")
        assert result["ok"] is False
    assert controller.typed == []


def test_verified_typing_rejects_control_characters_unicode_and_oversized_text():
    controller = FakeController()
    observer = FakeObserver([fp("")])
    for value in ("line\nbreak", "tab\tchar", "café", "x" * 501, ""):
        result = type_into_empty_focused_control(controller, observer, value)
        assert result["ok"] is False
        assert result["error"] == "desktop_text_must_be_printable_ascii_under_501_chars"
    assert controller.typed == []


def test_verified_typing_postcondition_fails_if_focus_changes_or_value_differs():
    controller = FakeController()
    before = fp("")
    result = type_into_empty_focused_control(controller, FakeObserver([before]), "hello")
    wrong_value = verify_desktop_typing(FakeObserver([fp("hello!")]), {"text": "hello"}, result)
    wrong_focus = verify_desktop_typing(FakeObserver([fp("hello", "b" * 64)]), {"text": "hello"}, result)
    assert wrong_value.ok is False
    assert wrong_focus.ok is False


def test_uia_preserves_unnamed_focused_edit_but_not_unnamed_actions():
    class Element:
        CurrentName = ""
        CurrentControlType = 50004
        CurrentIsEnabled = True
        CurrentIsOffscreen = False
        CurrentHasKeyboardFocus = True
        CurrentIsPassword = False

    items = WindowsUIAutomation._collect
    # The private collector's behavior is tested with a small fake UIA tree.
    element = Element()
    class Array:
        Length = 1
        def GetElement(self, index):
            assert index == 0
            return element
    class Window:
        def FindAll(self, scope, condition):
            return Array()
    class Automation:
        def CreateTrueCondition(self):
            return object()
    found = items(FakeModule, Automation(), Window())
    assert len(found) == 1 and found[0]["focused"] is True and found[0]["name"] == ""


class FakeModule:
    TreeScope_Subtree = 7
