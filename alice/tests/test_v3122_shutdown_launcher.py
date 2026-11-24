from pathlib import Path
from alice.ui.app import AliceUI


def test_shutdown_commands_are_local_and_immediate():
    accepted = [
        "shutdown", "shut down", "exit", "quit", "close", "close alice",
        "turn off", "turn off alice", "alice shutdown", "alice shut down",
        "shutdown alice", "alice turn off", "alice exit", "alice quit",
        "goodbye alice", "bye alice",
    ]
    for command in accepted:
        assert AliceUI._is_shutdown_command(command), command


def test_shutdown_phrases_are_not_overbroad():
    rejected = [
        "shutdown later", "alice shutdown later", "how do i shut down windows",
        "tell me how to quit", "quit the browser", "close chrome",
    ]
    for command in rejected:
        assert not AliceUI._is_shutdown_command(command), command


def test_close_button_keeps_alice_warm_and_explicit_shutdown_is_available():
    text = Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert 'self.root.protocol("WM_DELETE_WINDOW", self.hide_window)' in text
    assert 'menu.add_command(label="Shutdown ALICE",command=self.shutdown)' in text


def test_updater_never_uses_pytest_cache_clear():
    text = Path("alice/deployment/updater.py").read_text(encoding="utf-8")
    assert "--cache-clear" not in text
    assert "no:cacheprovider" in text


def test_persistent_launcher_exists_and_is_configured():
    launcher = Path("alice/desktop/launcher.py").read_text(encoding="utf-8")
    repair = Path("REPAIR_ALICE_STARTUP.bat").read_text(encoding="utf-8")
    assert "RegisterHotKey" in launcher
    assert "GetAsyncKeyState" in launcher
    assert "Alice Launcher.lnk" in repair
    assert "alice.desktop.launcher" in repair
    assert "CTRL+ALT+A" in repair
    assert 'start "" "%PYTHONW%" -m alice.desktop.launcher' in repair
