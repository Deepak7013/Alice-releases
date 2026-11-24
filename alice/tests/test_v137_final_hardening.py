import importlib
from pathlib import Path


def test_package_main_import_has_no_gui_side_effect(monkeypatch):
    calls = []
    import alice.ui.app as app
    monkeypatch.setattr(app, "main", lambda: calls.append("started"))
    mod = importlib.import_module("alice.__main__")
    importlib.reload(mod)
    assert calls == []


def test_screen_grounder_tool_can_be_called_without_injected_function(tmp_path, monkeypatch):
    from alice.vision.grounding import ScreenGrounder

    target = tmp_path / "screen.bin"
    target.write_bytes(b"first")
    calls = []

    def fake_screenshot(path):
        calls.append(path)
        Path(path).write_bytes(target.read_bytes())
        return {"ok": True, "path": str(path)}

    monkeypatch.setattr("alice.vision.screen.screenshot", fake_screenshot)
    g = ScreenGrounder()
    first = g.capture(path=target)
    second = g.capture(path=target)
    target.write_bytes(b"second")
    third = g.capture(path=target)

    assert first["ok"] and first["changed"] is False
    assert second["ok"] and second["changed"] is False
    assert third["ok"] and third["changed"] is True
    assert len(calls) == 3


def test_permission_manager_rejects_shell_metacharacter_bypass():
    from alice.security.permissions import PermissionManager

    p = PermissionManager()
    assert p.is_safe_command("python --version")
    assert not p.is_safe_command("python --version & del important.txt")
    assert not p.is_safe_command("dir | findstr secret")
    assert not p.is_safe_command("where python > output.txt")


def test_router_reports_unavailable_when_local_service_is_absent(monkeypatch):
    from alice.providers.router import Router
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")

    for key in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
        "OPENROUTER_API_KEY", "LOCAL_AI_BASE_URL", "ALICE_ENABLE_LOCAL_AI",
        "OPENAI_MODEL", "ALICE_PROVIDER", "ALICE_PRIMARY_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)
    # This test covers an absent local service. On developer PCs Ollama may be
    # installed and auto-detected, which is now the intended default behavior.
    monkeypatch.setattr(Router, "_local_service_detected", staticmethod(lambda: False))
    r = Router()
    assert r.available()["local"] is False
    assert r.primary_provider() is None
    assert r.local_model == "llama3.2:latest"


def test_router_local_provider_can_be_explicitly_enabled(monkeypatch):
    from alice.providers.router import Router
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ALICE_ENABLE_LOCAL_AI", "1")
    monkeypatch.setenv("LOCAL_AI_BASE_URL", "http://localhost:11434/v1")
    r = Router()
    monkeypatch.setattr(r,"local_status",lambda:{
        "reachable":True,"model_available":True,"models":["llama3.2:latest"]})
    assert r.available()["local"] is True
    assert r.primary_provider() == "local"
