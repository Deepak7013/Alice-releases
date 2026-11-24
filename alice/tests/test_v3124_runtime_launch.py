from pathlib import Path


def test_entrypoint_anchors_runtime_to_install_root():
    text = Path("alice/__main__.py").read_text(encoding="utf-8")
    assert "os.chdir(_ROOT)" in text
    assert "load_dotenv(env_file, override=True)" in text
    assert "ALICE_GLUTTONY_UI_V3128" in text


def test_router_uses_local_model_settings_from_runtime_environment(monkeypatch):
    from alice.providers.router import Router

    text = Path("alice/providers/router.py").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parents[2]" in text
    assert "LOCAL_AI_MODEL" in text
    monkeypatch.setenv("LOCAL_AI_MODEL", "llama3.2:latest")
    monkeypatch.setattr(Router, "_local_service_detected", staticmethod(lambda: False))
    assert Router().local_model == "llama3.2:latest"


def test_startup_uses_one_persistent_helper_not_direct_ui():
    text = Path("INSTALL_ALICE_STARTUP.bat").read_text(encoding="utf-8")
    assert "-m alice.desktop.launcher" in text
    assert '"-m alice --hidden"' not in text


def test_repair_replaces_legacy_startup_helper():
    text = Path("REPAIR_ALICE_STARTUP.bat").read_text(encoding="utf-8")
    assert 'schtasks /Delete /TN "ALICE Gluttony"' in text
    assert "-m alice.desktop.launcher" in text
