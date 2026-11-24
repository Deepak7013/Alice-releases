import hashlib
from pathlib import Path

from alice.agent.executor import Executor
from alice.computer.verified_keyboard import (
    press_key_with_expected_text,
    verify_verified_desktop_keypress,
)
from alice.execution.postconditions import PostconditionRegistry
from alice.tools.registry import ToolRegistry


class Controller:
    def __init__(self):
        self.keys = []

    def press(self, key):
        self.keys.append(key)


class Observer:
    def __init__(self, *snapshots):
        self.snapshots = iter(snapshots)

    def visible_texts(self):
        return next(self.snapshots)


def test_verified_keypress_requires_absent_baseline_and_allowlisted_key():
    controller = Controller()
    result = press_key_with_expected_text(controller, Observer(["Home"]), " Enter ", "Loaded")
    assert result["ok"] is True
    assert result["key"] == "enter"
    assert controller.keys == ["enter"]

    assert press_key_with_expected_text(controller, Observer(["Loaded"]), "enter", "Loaded")["error"] == "expected_text_already_visible"
    assert press_key_with_expected_text(controller, Observer([]), "delete", "Loaded")["error"] == "unsupported_verified_desktop_key"
    assert controller.keys == ["enter"]


def test_verified_keypress_observer_binds_action_and_hashes_expected_text():
    controller = Controller()
    expected = "Dashboard opened"
    result = press_key_with_expected_text(controller, Observer([], [expected]), "enter", expected)
    check = verify_verified_desktop_keypress(
        Observer([expected]), {"key": "enter", "expected_text": expected}, result
    )
    assert check.ok is True
    assert check.evidence == {
        "observed": True,
        "expected_text_visible": True,
        "expected_text_sha256": hashlib.sha256(expected.casefold().encode()).hexdigest(),
        "key": "enter",
    }
    assert expected not in repr(check.evidence)

    missing = verify_verified_desktop_keypress(
        Observer(["Home"]), {"key": "enter", "expected_text": expected}, result
    )
    tampered = verify_verified_desktop_keypress(
        Observer([expected]), {"key": "escape", "expected_text": expected}, result
    )
    assert not missing.ok and not tampered.ok


def test_active_tool_executor_marks_keypress_verified_only_after_readback():
    controller = Controller()
    observer = Observer([], ["Dashboard opened"])
    tools = ToolRegistry()
    tools.add("desktop_press_verified", "Verified desktop key", lambda key, expected_text:
              press_key_with_expected_text(controller, observer, key, expected_text), "execute")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register("desktop_press_verified", lambda args, result:
        verify_verified_desktop_keypress(observer, args, result))

    result = Executor(tools).run({"steps": [{
        "tool": "desktop_press_verified",
        "args": {"key": "enter", "expected_text": "Dashboard opened"},
    }]})[0]

    assert controller.keys == ["enter"]
    assert result["status"] == "verified"
    assert result["verified"] is True
    assert result["postcondition"]["evidence"]["observed"] is True
    assert "_postcondition_context" not in result["result"]


def test_current_app_registers_verified_keypress_tool_and_postcondition():
    source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert 't.add("desktop_press_verified"' in source
    assert 't.postconditions.register("desktop_press_verified"' in source
