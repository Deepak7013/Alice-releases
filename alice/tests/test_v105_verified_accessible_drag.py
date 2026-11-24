from pathlib import Path

from alice.agent.executor import Executor
from alice.computer.verified_drag import (
    drag_accessible_element,
    verify_accessible_drag_postcondition,
)
from alice.computer.uia import WindowsUIAutomation
from alice.execution.postconditions import PostconditionRegistry
from alice.tools.registry import ToolRegistry


class FakeController:
    def __init__(self, observer):
        self.observer = observer
        self.calls = []

    def screen_size(self):
        return {"width": 800, "height": 600}

    def drag(self, x1, y1, x2, y2, duration=0.5):
        self.calls.append((x1, y1, x2, y2, duration))
        if self.observer.move_on_drag:
            self.observer.current = self.observer.after


class FakeObserver:
    def __init__(self, *, duplicate_source=False, move_on_drag=True):
        self.source = {"name": "Report.csv", "role": "list_item", "enabled": True,
                       "bounds": [10, 10, 50, 50], "identity_sha256": "a" * 64}
        self.target = {"name": "Archive", "role": "list", "enabled": True,
                       "bounds": [300, 200, 500, 400], "identity_sha256": "b" * 64}
        self.after = [
            {**self.source, "bounds": [340, 240, 380, 280]},
            self.target,
        ]
        self.current = [self.source, self.target]
        if duplicate_source:
            self.current.append({**self.source, "identity_sha256": "c" * 64})
        self.move_on_drag = move_on_drag
        self.reads = []

    def visible_element_bounds(self, name, role):
        self.reads.append((name, role))
        return [row for row in self.current if row["name"].casefold() == name.casefold()
                and row["role"] == role]


def _registered(observer, controller):
    tools = ToolRegistry()
    tools.add("desktop_drag_accessible", "Drag and verify an accessible item",
              lambda **kwargs: drag_accessible_element(controller, observer, **kwargs), "execute")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register("desktop_drag_accessible",
        lambda args, result: verify_accessible_drag_postcondition(observer, args, result))
    executor = Executor(tools)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    return executor


def test_accessible_drag_reports_verified_only_after_fresh_target_readback():
    observer = FakeObserver()
    controller = FakeController(observer)
    result = _registered(observer, controller).run({"steps": [{
        "tool": "desktop_drag_accessible",
        "args": {"source_name": "Report.csv", "target_name": "Archive"},
    }]})[0]

    assert result["status"] == "verified"
    assert controller.calls == [(30, 30, 400, 300, 0.5)]
    assert observer.reads == [
        ("Report.csv", "list_item"), ("Archive", "list"),
        ("Report.csv", "list_item"), ("Archive", "list"),
    ]
    evidence = result["postcondition"]["evidence"]
    assert evidence["source_center_inside_target"] is True
    assert evidence["source_identity_matches"] is True
    assert "Report.csv" not in str(evidence)


def test_accessible_drag_stays_attempted_when_fresh_geometry_does_not_move():
    observer = FakeObserver(move_on_drag=False)
    controller = FakeController(observer)
    result = _registered(observer, controller).run({"steps": [{
        "tool": "desktop_drag_accessible",
        "args": {"source_name": "Report.csv", "target_name": "Archive"},
    }]})[0]

    assert controller.calls
    assert result["status"] == "attempted"
    assert result["verified"] is False
    assert result["postcondition"]["ok"] is False


def test_accessible_drag_rejects_ambiguous_source_before_mutation():
    observer = FakeObserver(duplicate_source=True)
    controller = FakeController(observer)
    result = drag_accessible_element(controller, observer, "Report.csv", "Archive")

    assert result["ok"] is False
    assert result["error"] == "accessible_drag_target_not_unique_or_observable"
    assert controller.calls == []


def test_accessible_drag_rejects_source_already_inside_target():
    observer = FakeObserver()
    observer.current[0] = {**observer.source, "bounds": [320, 220, 360, 260]}
    controller = FakeController(observer)

    result = drag_accessible_element(controller, observer, "Report.csv", "Archive")

    assert result["ok"] is False
    assert result["error"] == "accessible_drag_source_already_inside_target"
    assert controller.calls == []


def test_accessible_drag_postcondition_rejects_changed_element_identity():
    observer = FakeObserver()
    controller = FakeController(observer)
    action = drag_accessible_element(controller, observer, "Report.csv", "Archive")
    observer.current = [{**observer.after[0], "identity_sha256": "d" * 64}, observer.target]

    check = verify_accessible_drag_postcondition(observer, {
        "source_name": "Report.csv", "target_name": "Archive",
    }, action)

    assert check.ok is False
    assert check.evidence["source_identity_matches"] is False


def test_app_registers_accessible_drag_with_independent_postcondition():
    source = Path(__file__).parents[1].joinpath("ui", "app.py").read_text(encoding="utf-8")
    assert 't.postconditions.register("desktop_drag_accessible"' in source
    assert 't.add("desktop_drag_accessible"' in source


def test_uia_geometry_observer_returns_only_exact_named_role_with_opaque_identity(monkeypatch):
    class Rect:
        left, top, right, bottom = 1, 2, 31, 42

    class Element:
        CurrentBoundingRectangle = Rect()

        @staticmethod
        def GetRuntimeId():
            return [7, 11, 13]

    observer = WindowsUIAutomation()
    monkeypatch.setattr(observer, "_connect", lambda: ("com", "module", "automation", "window"))
    monkeypatch.setattr(observer, "_close", lambda _comtypes: None)
    monkeypatch.setattr(observer, "_collect", lambda *_: [
        {"name": "Report.csv", "control_type": 50007, "enabled": True,
         "element": Element()},
        {"name": "Report.csv", "control_type": 50020, "enabled": True,
         "element": Element()},
        {"name": "Other", "control_type": 50007, "enabled": True,
         "element": Element()},
    ])

    rows = observer.visible_element_bounds("Report.csv", "list_item")

    assert rows[0]["bounds"] == [1, 2, 31, 42]
    assert rows[0]["role"] == "list_item"
    assert len(rows[0]["identity_sha256"]) == 64
    assert len(rows) == 1


def test_uia_geometry_observer_fails_closed_when_tree_hits_collection_limit(monkeypatch):
    observer = WindowsUIAutomation()
    monkeypatch.setattr(observer, "_connect", lambda: ("com", "module", "automation", "window"))
    monkeypatch.setattr(observer, "_close", lambda _comtypes: None)
    monkeypatch.setattr(observer, "_collect", lambda *_: [
        {"name": "Report.csv", "control_type": 50007, "enabled": True,
         "element": object()},
    ] * observer._MAX_ELEMENTS)

    assert observer.visible_element_bounds("Report.csv", "list_item") == []


def test_accessible_drag_postcondition_rejects_forged_overlapping_baseline():
    observer = FakeObserver()
    controller = FakeController(observer)
    action = drag_accessible_element(controller, observer, "Report.csv", "Archive")
    action["_postcondition_context"]["source_before_bounds"] = [320, 220, 360, 260]

    check = verify_accessible_drag_postcondition(observer, {
        "source_name": "Report.csv", "target_name": "Archive",
    }, action)

    assert check.ok is False
    assert check.reason == "accessible_drag_baseline_invalid"
