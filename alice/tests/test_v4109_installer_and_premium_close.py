import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_installer_runs_manifest_verification_from_staged_application_root():
    script = (ROOT / "INSTALL_ALICE.ps1").read_text(encoding="utf-8")
    verify_call = "-m alice.deployment.installer_verify --root $Stage"
    assert "Push-Location $Stage" in script
    assert verify_call in script
    assert "$verifyRc = $LASTEXITCODE" in script
    assert "if ($verifyRc -ne 0)" in script
    assert "Persistent diagnostic log" in script
    assert '"C:\\Alice_v4.109.0"' in script


def test_premium_window_close_stops_hidden_runtime_and_is_idempotent():
    from alice.ui.app import _close_premium_runtime

    class Root:
        def __init__(self):
            self.calls = []

        def after(self, delay, callback):
            self.calls.append((delay, callback))

        def quit(self):
            pass

    class App:
        def __init__(self):
            self.root = Root()
            self._shutdown = False

    app = App()
    holder = {"app": app}
    _close_premium_runtime(holder)
    _close_premium_runtime(holder)

    assert app._shutdown is True
    assert len(app.root.calls) == 1
    assert app.root.calls[0][0] == 0


def test_premium_window_close_signals_tk_thread_without_cross_thread_tk_call():
    from alice.ui.app import _close_premium_runtime

    class Root:
        def __init__(self):
            self.calls = []

        def after(self, delay, callback):
            self.calls.append((delay, callback))

    class App:
        def __init__(self):
            self.root = Root()
            self._shutdown = False

    app = App()
    close_event = threading.Event()
    _close_premium_runtime({"app": app, "close_event": close_event})

    assert close_event.is_set()
    assert app._shutdown is True
    assert app._premium_window_closed is True
    assert app.root.calls == []


def test_premium_settings_opens_local_preferences_and_brain_setup():
    html = (ROOT / "alice" / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")
    bridge = (ROOT / "alice" / "ui" / "premium_bridge.py").read_text(encoding="utf-8")
    app = (ROOT / "alice" / "ui" / "app.py").read_text(encoding="utf-8")
    assert 'id="providerDialog"' in html
    assert "providerDialog.showModal()" in html
    assert "save_provider_settings" not in html
    assert "AI provider API keys are not accepted" in bridge
    assert '"premium_provider_saved"' not in bridge
    assert "ALICE Brain · Gemini primary" in app


def test_premium_workspace_routes_chat_tools_updates_voice_and_text_attachments():
    html = (ROOT / "alice" / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")
    bridge = (ROOT / "alice" / "ui" / "premium_bridge.py").read_text(encoding="utf-8")
    app = (ROOT / "alice" / "ui" / "app.py").read_text(encoding="utf-8")
    assert 'data-view="Tools"' in html and 'data-view="Updates"' in html
    assert 'data-view="Voice"' in html and 'id="speakModeBtn"' in html
    assert 'id="chatMount"' in html and "conversation-inline" in html
    assert 'id="attachmentInput"' in html and "file.size>65536" in html
    assert "open_native_panel" in bridge and "set_speak_mode" in bridge
    assert '"premium_native_panel"' in app and '"premium_speak_mode"' in app
