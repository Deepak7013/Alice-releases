from pathlib import Path
import inspect

ROOT=Path(__file__).resolve().parents[2]

def test_version_is_v352():
    assert (ROOT/"VERSION.txt").read_text().strip().startswith("ALICE v")

def test_launcher_repair_is_root_relative_and_version_neutral():
    text=(ROOT/"alice/deployment/launcher_repair.py").read_text(encoding="utf-8")
    assert "ALICE_REPAIR_ROOT" in text
    assert "Alice - Restart.lnk" in text
    assert "ALICE Gluttony" in text
    assert "C:\\Alice_v3.33.0" not in text
    assert "v3.35.1" not in text

def test_update_helper_repairs_launcher_before_visible_restart():
    text=(ROOT/"alice/deployment/update_helper.py").read_text(encoding="utf-8")
    assert "repair_windows_launchers(root, start_visible=False)" in text
    assert '[str(launcher), "-m", "alice", "--show"]' in text
    assert '[str(launcher), "-m", "alice", "--hidden"]' not in text

def test_startup_repair_is_not_hardcoded_to_a_release_folder():
    text=(ROOT/"REPAIR_ALICE_STARTUP.bat").read_text(encoding="utf-8")
    assert "%~dp0" in text
    assert "repair_windows_launchers" in text
    assert "C:\\Alice_v3.35.1" not in text
