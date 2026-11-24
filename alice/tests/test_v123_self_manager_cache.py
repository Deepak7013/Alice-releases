from pathlib import Path


def test_self_manager_does_not_clear_pytest_cache():
    text = (Path(__file__).resolve().parents[1] / "maintenance" / "self_manager.py").read_text(encoding="utf-8")
    assert "--cache-clear" not in text
    assert '"no:cacheprovider"' in text


def test_ui_version_is_current():
    text = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert "v3.35.5" not in text
