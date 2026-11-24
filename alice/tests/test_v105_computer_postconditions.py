import subprocess

from alice.computer.discovery import AppDiscovery
from alice.computer.postconditions import verify_open_app_postcondition
from alice.computer.windows import open_app


class Discovery:
    def __init__(self, result):
        self.result = result
        self.pids = []

    def process_by_pid(self, pid):
        self.pids.append(pid)
        return self.result


def test_open_app_requires_requested_pid_and_exact_image():
    discovery = Discovery({"ok": True, "processes": [{"image": "notepad.exe", "pid": 8124}]})
    check = verify_open_app_postcondition(
        discovery,
        {"command": '"C:\\Windows\\System32\\notepad.exe"'},
        {"ok": True, "action": "open_app", "target": '"C:\\Windows\\System32\\notepad.exe"', "pid": 8124},
    )
    assert check.ok
    assert discovery.pids == [8124]
    assert check.evidence["pid_bound"] is True


def test_open_app_rejects_old_same_image_with_different_pid():
    discovery = Discovery({"ok": True, "processes": [{"image": "notepad.exe", "pid": 100}]})
    check = verify_open_app_postcondition(
        discovery, {"command": "notepad.exe"},
        {"ok": True, "action": "open_app", "target": "notepad.exe", "pid": 101},
    )
    assert not check.ok


def test_open_app_rejects_pid_image_mismatch_or_failed_readback():
    mismatch = Discovery({"ok": True, "processes": [{"image": "calc.exe", "pid": 8124}]})
    failed = Discovery({"ok": False, "processes": []})
    result = {"ok": True, "action": "open_app", "target": "notepad.exe", "pid": 8124}
    assert not verify_open_app_postcondition(mismatch, {"command": "notepad.exe"}, result).ok
    assert not verify_open_app_postcondition(failed, {"command": "notepad.exe"}, result).ok


def test_open_app_rejects_result_bound_to_another_command():
    discovery = Discovery({"ok": True, "processes": [{"image": "notepad.exe", "pid": 8124}]})
    check = verify_open_app_postcondition(
        discovery, {"command": "notepad.exe"},
        {"ok": True, "action": "open_app", "target": "calc.exe", "pid": 8124},
    )
    assert not check.ok
    assert discovery.pids == []


def test_open_app_returns_pid_from_the_started_process(monkeypatch):
    class Started:
        pid = 4567

    monkeypatch.setattr(subprocess, "Popen", lambda command, shell: Started())
    result = open_app("notepad.exe")
    assert result == {"ok": True, "action": "open_app", "target": "notepad.exe", "pid": 4567}


def test_absolute_executable_with_spaces_is_launched_and_verified_as_one_path(monkeypatch):
    command=r"C:\Users\ALICE-Test\AppData\Local\Programs\Ollama\ollama app.exe"
    calls=[]
    class Started:
        pid=4567
    def fake_popen(value, shell):
        calls.append((value,shell))
        return Started()
    monkeypatch.setattr(subprocess,"Popen",fake_popen)
    result=open_app(command)
    assert calls == [([command],False)]
    discovery=Discovery({"ok":True,"processes":[{"image":"ollama app.exe","pid":4567}]})
    assert verify_open_app_postcondition(discovery,{"command":command},result).ok


def test_process_by_pid_uses_native_exact_pid_filter(monkeypatch):
    calls = []

    def check_output(command, **kwargs):
        calls.append(command)
        return '"notepad.exe","8124","Console","1","12,000 K"\n'

    monkeypatch.setattr(subprocess, "check_output", check_output)
    result = AppDiscovery().process_by_pid(8124)
    assert result == {"ok": True, "processes": [{"image": "notepad.exe", "pid": 8124}]}
    assert calls == [["tasklist", "/FO", "CSV", "/NH", "/FI", "PID eq 8124"]]


def test_process_by_pid_rejects_nonmatching_csv_row(monkeypatch):
    monkeypatch.setattr(subprocess, "check_output", lambda *_a, **_k: '"notepad.exe","18124"\n')
    assert AppDiscovery().process_by_pid(8124)["processes"] == []


def test_active_open_app_tool_registers_the_independent_observer():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert "from ..computer.postconditions import verify_open_app_postcondition" in source
    assert 't.postconditions.register("open_app",lambda args,result:verify_open_app_postcondition(discovery,args,result))' in source

