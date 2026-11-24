import importlib


def test_windows_launcher_api_exists():
    mod = importlib.import_module("alice.computer.windows")
    assert callable(mod.open_app)
    assert callable(mod.open_url)


def test_url_launcher_rejects_unsafe_scheme():
    from alice.computer.windows import open_url
    result = open_url("file:///etc/passwd")
    assert result["ok"] is False


def test_ui_main_is_importable():
    mod = importlib.import_module("alice.ui.app")
    assert callable(mod.main)
