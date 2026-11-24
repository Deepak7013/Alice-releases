from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_version_is_v353():
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() .startswith("ALICE v")


def test_relaunch_helper_uses_real_python_and_diagnostics():
    text = (ROOT / "alice/deployment/update_helper.py").read_text(encoding="utf-8")
    assert '"--show"' in text
    assert "upgrade_relaunch.log" in text
    assert "upgrade_relaunch_diagnostics.json" in text
    assert "CREATE_NO_WINDOW" in text
    assert "health_data.get(\"version\") == result.get(\"version\")" in text


def test_relaunch_helper_does_not_silently_finish_on_health_failure():
    text = (ROOT / "alice/deployment/update_helper.py").read_text(encoding="utf-8")
    assert "post_restart_health_timeout" in text
    assert "rollback" in text
    assert "stdout_stderr_tail" in text


def test_launcher_repair_is_active_root_relative():
    text = (ROOT / "alice/deployment/launcher_repair.py").read_text(encoding="utf-8")
    assert "ALICE_REPAIR_ROOT" in text
    assert "ALICE_REPAIR_PYTHONW" in text
    assert "C:\\Alice_v3.33.0" not in text
