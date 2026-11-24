from pathlib import Path

from alice.agent.executor import Executor
from alice.computer.verified_mouse import (
    move_pointer_to_verified,
    verify_pointer_position_postcondition,
)
from alice.execution.postconditions import PostconditionRegistry
from alice.tools.registry import ToolRegistry


class FakePointer:
    def __init__(self, *, move=True):
        self.position = {"x": 1, "y": 2}
        self.move_enabled = move
        self.calls = []

    def screen_size(self):
        return {"width": 640, "height": 480}

    def move(self, x, y, duration=0.2):
        self.calls.append((x, y, duration))
        if self.move_enabled:
            self.position = {"x": x, "y": y}

    def mouse_position(self):
        return dict(self.position)


def _executor(pointer):
    tools = ToolRegistry()
    tools.add("desktop_move_verified", "Move and verify pointer",
              lambda **args: move_pointer_to_verified(pointer, **args), "execute")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register("desktop_move_verified",
        lambda args, result: verify_pointer_position_postcondition(pointer, args, result))
    executor = Executor(tools)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    return executor


def test_pointer_move_is_verified_by_fresh_position_readback():
    pointer = FakePointer()
    result = _executor(pointer).run({"steps": [{
        "tool": "desktop_move_verified", "args": {"x": 120, "y": 300},
    }]})[0]

    assert result["status"] == "verified"
    assert result["postcondition"]["evidence"] == {
        "observed": True, "position_matches": True, "requested_x": 120, "requested_y": 300,
    }
    assert pointer.calls == [(120, 300, 0.2)]


def test_pointer_move_stays_attempted_when_position_did_not_change():
    pointer = FakePointer(move=False)
    result = _executor(pointer).run({"steps": [{
        "tool": "desktop_move_verified", "args": {"x": 120, "y": 300},
    }]})[0]

    assert result["status"] == "attempted"
    assert result["verified"] is False
    assert result["postcondition"]["ok"] is False


def test_pointer_move_rejects_out_of_bounds_and_non_integer_values_before_action():
    for x, y in ((640, 10), (-1, 10), (1.5, 10), (True, 10)):
        pointer = FakePointer()
        result = move_pointer_to_verified(pointer, x, y)
        assert result["ok"] is False
        assert pointer.calls == []


def test_pointer_move_postcondition_rejects_result_target_mismatch():
    pointer = FakePointer()
    action = move_pointer_to_verified(pointer, 120, 300)

    check = verify_pointer_position_postcondition(pointer, {"x": 121, "y": 300}, action)

    assert check.ok is False
    assert check.evidence == {"observed": False}


def test_app_registers_pointer_move_with_independent_readback():
    source = Path(__file__).parents[1].joinpath("ui", "app.py").read_text(encoding="utf-8")
    assert 't.postconditions.register("desktop_move_verified"' in source
    assert 't.add("desktop_move_verified"' in source
