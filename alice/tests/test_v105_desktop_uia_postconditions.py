import hashlib
from pathlib import Path

from alice.computer.postconditions import verify_accessible_click_postcondition
from alice.computer.uia import WindowsUIAutomation


class FakePattern:
    def __init__(self):
        self.invoked = False

    def Invoke(self):
        self.invoked = True


class FakeRect:
    left = 10
    top = 20
    right = 31
    bottom = 41


class FakeElement:
    def __init__(self, name, control_type=50000, enabled=True, offscreen=False, password=False):
        self.CurrentName = name
        self.CurrentControlType = control_type
        self.CurrentIsEnabled = enabled
        self.CurrentIsOffscreen = offscreen
        self.CurrentIsPassword = password
        self.CurrentHasKeyboardFocus = False
        self.CurrentBoundingRectangle = FakeRect()
        self.runtime_id = [id(self) & 0x7fffffff]
        self.pattern = FakePattern()

    def GetRuntimeId(self):
        return self.runtime_id

    def GetCurrentPattern(self, _pattern):
        return self.pattern


class FakeArray:
    def __init__(self, elements):
        self.elements = elements
        self.Length = len(elements)

    def GetElement(self, index):
        return self.elements[index]


class FakeAutomation:
    def __init__(self):
        self.condition = object()

    def CreateTrueCondition(self):
        return self.condition


class FakeComtypes:
    def __init__(self):
        self.uninitialized = 0

    def CoUninitialize(self):
        self.uninitialized += 1


class FakeModule:
    TreeScope_Subtree = 7
    UIA_InvokePatternId = 10000


class FakeWindow:
    def __init__(self, elements):
        self.CurrentNativeWindowHandle = 123
        self.array = FakeArray(elements)

    def FindAll(self, scope, condition):
        assert scope == FakeModule.TreeScope_Subtree
        assert condition is not None
        return self.array


class FakeController:
    def __init__(self):
        self.clicked = []

    def screen_size(self):
        return {"width": 100, "height": 100}

    def is_foreground_window(self, hwnd):
        return hwnd == 123

    def click(self, x, y):
        self.clicked.append((x, y))


def _observer(elements):
    controller = FakeController()
    observer = WindowsUIAutomation(controller=controller)
    comtypes = FakeComtypes()
    automation = FakeAutomation()
    observer._connect = lambda: (comtypes, FakeModule, automation, FakeWindow(elements))
    observer.test_controller = controller
    return observer, comtypes


def test_click_exact_invokes_one_visible_enabled_accessible_button():
    button = FakeElement("Settings")
    observer, comtypes = _observer([button, FakeElement("Password", password=True)])

    result = observer.click_exact("Settings", "Settings opened")

    assert result["ok"] is True
    assert result["action"] == "desktop_click_accessible"
    assert button.pattern.invoked is False
    assert observer.test_controller.clicked == [(20, 30)]
    assert result["_postcondition_context"]["expected_absent_before"] is True
    assert result["target_sha256"] == hashlib.sha256(b"settings").hexdigest()
    assert comtypes.uninitialized == 1


def test_click_exact_fails_closed_for_ambiguous_disabled_or_old_text():
    ambiguous, _ = _observer([FakeElement("Continue"), FakeElement("Continue")])
    disabled, _ = _observer([FakeElement("Continue", enabled=False)])
    old_text, _ = _observer([FakeElement("Continue"), FakeElement("Continue selected")])

    assert ambiguous.click_exact("Continue", "Next page")["error"] == "accessibility_target_not_unique"
    assert disabled.click_exact("Continue", "Next page")["error"] == "accessibility_target_not_unique"
    assert old_text.click_exact("Continue", "Continue selected")["error"] == "expected_text_already_visible"


def test_click_exact_rejects_unsupported_roles_and_sensitive_targets():
    observer, _ = _observer([FakeElement("Continue")])
    assert observer.click_exact("Continue", "Next page", "Text")["ok"] is False
    assert observer.click_exact("Continue", "")["ok"] is False


def test_accessible_click_postcondition_uses_fresh_readback_and_hash_only_evidence():
    class Observer:
        def visible_texts(self):
            return ["Welcome", "Settings opened"]

    target = "Settings"
    expected = "Settings opened"
    result = {"ok": True, "action": "desktop_click_accessible",
              "target_sha256": hashlib.sha256(target.casefold().encode()).hexdigest(),
              "_postcondition_context": {"expected_absent_before": True,
                  "expected_text_sha256": hashlib.sha256(expected.casefold().encode()).hexdigest()}}
    check = verify_accessible_click_postcondition(Observer(),
        {"name": target, "expected_text": expected}, result)
    assert check.ok
    assert check.evidence["expected_text_visible"] is True
    assert expected not in repr(check.evidence)


def test_accessible_click_postcondition_rejects_old_binding_or_missing_transition():
    class Observer:
        def visible_texts(self):
            return ["Welcome"]

    target = "Settings"
    expected = "Settings opened"
    result = {"ok": True, "action": "desktop_click_accessible",
              "target_sha256": hashlib.sha256(target.casefold().encode()).hexdigest(),
              "_postcondition_context": {"expected_absent_before": True,
                  "expected_text_sha256": hashlib.sha256(expected.casefold().encode()).hexdigest()}}
    check = verify_accessible_click_postcondition(Observer(),
        {"name": target, "expected_text": expected}, result)
    assert not check.ok
    result["_postcondition_context"]["expected_absent_before"] = False
    assert not verify_accessible_click_postcondition(Observer(),
        {"name": target, "expected_text": expected}, result).ok


def test_active_app_registers_accessibility_click_observer():
    source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert "from ..computer.uia import WindowsUIAutomation" in source
    assert 't.add("desktop_click_accessible"' in source
    assert 't.postconditions.register("desktop_click_accessible"' in source


def test_collect_caps_foreground_tree_and_excludes_password_offscreen_and_blank_names():
    visible = [FakeElement(f"Control {index}") for index in range(305)]
    visible.extend([
        FakeElement("Hidden target", offscreen=True),
        FakeElement("Secret field", password=True),
        FakeElement("   "),
    ])
    observer, _ = _observer(visible)
    _comtypes, module, automation, window = observer._connect()

    collected = observer._collect(module, automation, window)

    assert len(collected) == WindowsUIAutomation._MAX_ELEMENTS
    assert all(item["name"] != "Hidden target" for item in collected)
    assert all(item["name"] != "Secret field" for item in collected)
    assert all(item["name"].strip() for item in collected)


def test_collect_bounds_accessible_name_length():
    observer, _ = _observer([FakeElement("x" * 500)])
    _comtypes, module, automation, window = observer._connect()

    collected = observer._collect(module, automation, window)

    assert len(collected) == 1
    assert len(collected[0]["name"]) == WindowsUIAutomation._MAX_NAME_CHARS


def test_accessible_root_prefers_webview_child_with_application_actions():
    shell = FakeWindow([FakeElement("Minimize")])
    content = FakeWindow([
        FakeElement("Conversation"),
        FakeElement("Settings"),
        FakeElement("Send to ALICE"),
    ])

    selected = WindowsUIAutomation._best_accessible_root(
        FakeModule, FakeAutomation(), [shell, content]
    )

    assert selected is content


def test_accessible_root_keeps_first_root_when_scores_are_equal():
    first = FakeWindow([FakeElement("Minimize")])
    duplicate = FakeWindow([FakeElement("Minimize")])

    selected = WindowsUIAutomation._best_accessible_root(
        FakeModule, FakeAutomation(), [first, duplicate]
    )

    assert selected is first


def test_visible_actions_returns_only_enabled_visible_buttons_and_links():
    elements = [
        FakeElement("Save", control_type=50000),
        FakeElement("Help", control_type=50005),
        FakeElement("Disabled", control_type=50000, enabled=False),
        FakeElement("Hidden", control_type=50000, offscreen=True),
        FakeElement("Text content", control_type=50004),
        FakeElement("Password", control_type=50000, password=True),
    ]
    observer, comtypes = _observer(elements)

    result = observer.visible_actions()

    assert result == {"ok": True, "actions": [
        {"name": "Save", "role": "button"},
        {"name": "Help", "role": "hyperlink"},
    ], "count": 2}
    assert comtypes.uninitialized == 1


def test_visible_actions_caps_returned_controls_at_100():
    observer, _ = _observer([FakeElement(f"Button {i}") for i in range(150)])

    result = observer.visible_actions()

    assert result["ok"] is True
    assert result["count"] == 100
    assert len(result["actions"]) == 100


def test_active_app_registers_read_only_desktop_action_observer():
    source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert 't.add("desktop_observe_actions"' in source
    assert 'WindowsUIAutomation().visible_actions,"read"' in source


def test_verified_coordinate_click_requires_absent_expected_text_and_bounds():
    from alice.computer.verified_click import click_with_expected_text

    class Controller:
        clicked = None
        def screen_size(self): return {"width": 100, "height": 80}
        def click(self, x, y): self.clicked = (x, y)

    class Observer:
        def __init__(self, names): self.names = names
        def visible_texts(self): return self.names

    controller = Controller()
    result = click_with_expected_text(controller, Observer(["Home"]), 20, 30, "Saved")
    assert result["ok"] is True
    assert controller.clicked == (20, 30)
    assert result["_postcondition_context"]["expected_absent_before"] is True
    assert click_with_expected_text(controller, Observer(["Saved"]), 20, 30, "Saved")["error"] == "expected_text_already_visible"
    assert click_with_expected_text(controller, Observer([]), 100, 30, "Saved")["error"] == "desktop_click_out_of_bounds"
    assert click_with_expected_text(controller, Observer([]), True, 30, "Saved")["ok"] is False


def test_verified_coordinate_click_postcondition_requires_fresh_text_transition():
    import hashlib
    from alice.computer.verified_click import verify_verified_desktop_click

    expected = "Saved successfully"
    result = {"ok": True, "action": "desktop_click_verified", "x": 10, "y": 12,
              "_postcondition_context": {"expected_absent_before": True,
                  "expected_text_sha256": hashlib.sha256(expected.casefold().encode()).hexdigest()}}

    class Observer:
        def __init__(self, names): self.names = names
        def visible_texts(self): return self.names

    passed = verify_verified_desktop_click(Observer(["Saved successfully"]),
        {"x": 10, "y": 12, "expected_text": expected}, result)
    failed = verify_verified_desktop_click(Observer(["Home"]),
        {"x": 10, "y": 12, "expected_text": expected}, result)
    assert passed.ok is True and passed.evidence["observed"] is True
    assert failed.ok is False
    assert expected not in repr(passed.evidence)


def test_active_app_registers_verified_coordinate_click_postcondition():
    source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert 't.add("desktop_click_verified"' in source
    assert 't.postconditions.register("desktop_click_verified"' in source


def test_verified_scroll_bounds_amount_and_requires_absent_expected_text():
    from alice.computer.verified_scroll import scroll_with_expected_text

    class Controller:
        def __init__(self): self.amounts = []
        def scroll(self, amount): self.amounts.append(amount)

    class Observer:
        def __init__(self, names): self.names = names
        def visible_texts(self): return self.names

    controller = Controller()
    result = scroll_with_expected_text(controller, Observer(["Top"]), 5, "Bottom")
    assert result["ok"] is True and result["action"] == "desktop_scroll_verified"
    assert controller.amounts == [5]
    assert scroll_with_expected_text(controller, Observer([]), 21, "Bottom")["ok"] is False
    assert scroll_with_expected_text(controller, Observer([]), 0, "Bottom")["ok"] is False
    assert scroll_with_expected_text(controller, Observer(["Bottom"]), 2, "Bottom")["error"] == "expected_text_already_visible"
    assert controller.amounts == [5]


def test_verified_scroll_postcondition_requires_fresh_bound_transition():
    import hashlib
    from alice.computer.verified_scroll import verify_verified_desktop_scroll

    expected = "Bottom of page"
    result = {"ok": True, "action": "desktop_scroll_verified", "amount": 3,
              "_postcondition_context": {"expected_absent_before": True,
                  "expected_text_sha256": hashlib.sha256(expected.casefold().encode()).hexdigest()}}

    class Observer:
        def __init__(self, names): self.names = names
        def visible_texts(self): return self.names

    passed = verify_verified_desktop_scroll(Observer(["Bottom of page"]),
        {"amount": 3, "expected_text": expected}, result)
    failed = verify_verified_desktop_scroll(Observer(["Top"]),
        {"amount": 3, "expected_text": expected}, result)
    mismatched = verify_verified_desktop_scroll(Observer([expected]),
        {"amount": 4, "expected_text": expected}, result)
    assert passed.ok is True and passed.evidence["observed"] is True
    assert failed.ok is False and mismatched.ok is False
    assert expected not in repr(passed.evidence)


def test_active_app_registers_verified_scroll_tool_and_postcondition():
    source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert 't.add("desktop_scroll_verified"' in source
    assert 't.postconditions.register("desktop_scroll_verified"' in source


def test_focused_control_returns_safe_metadata_and_never_edit_value():
    button = FakeElement("Continue")
    button.CurrentHasKeyboardFocus = False
    edit = FakeElement("private form contents", control_type=50004)
    edit.CurrentHasKeyboardFocus = True
    observer, comtypes = _observer([button, edit])
    result = observer.focused_control()
    assert result["ok"] is True
    assert result["role"] == "edit"
    assert result["editable"] is True
    assert result["name"] == ""
    assert "private form contents" not in repr(result)
    assert len(result["focus_sha256"]) == 64
    assert comtypes.uninitialized == 1


def test_focused_control_fails_closed_when_focus_is_ambiguous():
    first = FakeElement("First")
    first.CurrentHasKeyboardFocus = True
    second = FakeElement("Second")
    second.CurrentHasKeyboardFocus = True
    observer, _ = _observer([first, second])
    assert observer.focused_control() == {"ok": False, "error": "focused_control_not_unique"}


def test_verified_tab_navigation_requires_changed_focus():
    from alice.computer.verified_keyboard import tab_to_next_focus, verify_focus_navigation

    class Controller:
        def __init__(self): self.calls = []
        def press(self, key): self.calls.append(("press", key))
        def hotkey(self, *keys): self.calls.append(("hotkey", *keys))
    class Observer:
        def __init__(self): self.digests = ["a" * 64, "b" * 64]
        def focused_control(self):
            return {"ok": True, "focus_sha256": self.digests.pop(0)}
    controller, observer = Controller(), Observer()
    result = tab_to_next_focus(controller, observer, "forward")
    assert result["ok"] is True
    assert controller.calls == [("press", "tab")]
    verified = verify_focus_navigation(observer, {"direction": "forward"}, result)
    assert verified.ok is True
    assert verified.evidence["focus_changed"] is True


def test_verified_shift_tab_and_no_transition_fails():
    from alice.computer.verified_keyboard import tab_to_next_focus, verify_focus_navigation

    class Controller:
        def __init__(self): self.calls = []
        def press(self, key): self.calls.append(("press", key))
        def hotkey(self, *keys): self.calls.append(("hotkey", *keys))
    class Observer:
        def __init__(self, values): self.values = iter(values)
        def focused_control(self): return {"ok": True, "focus_sha256": next(self.values)}
    controller, observer = Controller(), Observer(["c" * 64, "c" * 64])
    result = tab_to_next_focus(controller, observer, "backward")
    assert controller.calls == [("hotkey", "shift", "tab")]
    verified = verify_focus_navigation(observer, {"direction": "backward"}, result)
    assert verified.ok is False
    assert verified.reason == "focus_transition_not_observed"


def test_verified_focus_navigation_rejects_invalid_direction_before_keypress():
    from alice.computer.verified_keyboard import tab_to_next_focus
    class Controller:
        def press(self, key): raise AssertionError("must not press")
        def hotkey(self, *keys): raise AssertionError("must not hotkey")
    class Observer:
        def focused_control(self): raise AssertionError("must not observe")
    result = tab_to_next_focus(Controller(), Observer(), "enter")
    assert result == {"ok": False, "error": "invalid_focus_navigation_direction"}


def test_focused_control_and_verified_focus_navigation_are_registered():
    source = Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert 't.add("desktop_focused_control"' in source
    assert 't.add("desktop_focus_navigate"' in source
    assert 't.postconditions.register("desktop_focus_navigate"' in source


def test_focus_fingerprint_distinguishes_same_type_edit_controls_without_exposing_values():
    first = FakeElement("secret first value", control_type=50004)
    first.CurrentHasKeyboardFocus = True
    second = FakeElement("secret second value", control_type=50004)
    second.CurrentHasKeyboardFocus = True
    first_observer, _ = _observer([first])
    second_observer, _ = _observer([second])
    first_result = first_observer.focused_control()
    second_result = second_observer.focused_control()
    assert first_result["ok"] is True and second_result["ok"] is True
    assert first_result["name"] == second_result["name"] == ""
    assert first_result["focus_sha256"] != second_result["focus_sha256"]
    assert "secret" not in repr(first_result) + repr(second_result)


def test_focused_control_fails_closed_if_runtime_id_unavailable():
    edit = FakeElement("private value", control_type=50004)
    edit.CurrentHasKeyboardFocus = True
    edit.GetRuntimeId = lambda: None
    observer, _ = _observer([edit])
    assert observer.focused_control() == {"ok": False, "error": "focused_control_runtime_id_unavailable"}
