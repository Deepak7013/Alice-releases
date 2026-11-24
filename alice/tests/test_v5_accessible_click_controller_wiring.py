import ctypes
from types import SimpleNamespace
from pathlib import Path

from alice.computer.controller import ComputerController


def test_computer_controller_accepts_foreground_window_or_its_child(monkeypatch):
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(
            GetForegroundWindow=lambda: 1234,
            GetAncestor=lambda hwnd, kind: 1234 if hwnd == 5678 and kind == 2 else hwnd,
        )),
        raising=False,
    )
    controller = ComputerController.__new__(ComputerController)

    assert controller.is_foreground_window(1234) is True
    assert controller.is_foreground_window(5678) is True
    assert controller.is_foreground_window(4321) is False
    assert controller.is_foreground_window(0) is False


def test_computer_controller_fails_closed_when_foreground_probe_fails(monkeypatch):
    monkeypatch.setattr(ctypes, "windll", None, raising=False)
    controller = ComputerController.__new__(ComputerController)

    assert controller.is_foreground_window(1234) is False
    assert controller.is_foreground_window("not-a-window") is False


def test_accessible_click_tool_is_bound_to_its_verified_controller():
    app_source = Path(__file__).resolve().parents[1].joinpath("ui", "app.py").read_text(encoding="utf-8")

    assert 'WindowsUIAutomation(pc).click_exact,"execute"' in app_source
