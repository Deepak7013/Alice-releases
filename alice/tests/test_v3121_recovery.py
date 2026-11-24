from pathlib import Path
from alice.deployment.updater import InPlaceUpdater


def test_transactional_tests_do_not_clear_pytest_cache():
    import inspect
    text = inspect.getsource(InPlaceUpdater._run_tests)
    assert "no:cacheprovider" in text
    assert "--cache-clear" not in text


def test_startup_repair_script_restores_shortcut_and_task():
    text = (Path(__file__).resolve().parents[2] / "REPAIR_ALICE_STARTUP.bat").read_text(encoding="utf-8")
    assert "Alice - Restart.lnk" in text
    assert "CTRL+ALT+A" in text
    assert "ALICE Gluttony" in text
    assert "-m alice --show" in text
