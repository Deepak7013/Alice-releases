from pathlib import Path
from alice.ui.app import AliceUI
from alice.desktop.control import GlobalHotkey
from alice.voice.voice import Voice


def test_shutdown_command_is_exact_and_safe():
    assert AliceUI._is_shutdown_command("Alice shutdown") is True
    assert AliceUI._is_shutdown_command("  ALICE   SHUT DOWN  ") is True
    assert AliceUI._is_shutdown_command("shutdown alice") is True
    assert AliceUI._is_shutdown_command("please shutdown alice") is False
    assert AliceUI._is_shutdown_command("alice shutdown later") is False


def test_startup_uses_quiet_hidden_mode_and_restart_shortcut():
    text=Path("INSTALL_ALICE_STARTUP.bat").read_text(encoding="utf-8")
    assert "ONLOGON" in text
    assert "-m alice.desktop.launcher" in text
    assert "CTRL+ALT+A" in text
    assert "Alice - Restart.lnk" in text


def test_run_launcher_can_show_full_ui():
    text=Path("RUN_ALICE.bat").read_text(encoding="utf-8")
    assert "-m alice --show" in text


def test_global_hotkey_contract():
    h=GlobalHotkey(lambda:None)
    assert callable(h.callback)
    assert h.vk==ord("A")


def test_voice_exposes_selectable_voice_contract():
    v=Voice(root=Path("."))
    assert callable(v.list_voices)
    assert callable(v.select_voice)
    assert callable(v.select_female_default)
    assert callable(v.ensure_female_default)
    assert callable(v.stop)
