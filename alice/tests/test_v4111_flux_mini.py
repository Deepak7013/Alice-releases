from pathlib import Path
import queue
import threading

from alice.ui.premium_bridge import PremiumUIBridge
from alice.ui.win_drop import normalize_dropped_paths


class FakeApp:
    def __init__(self, root_path=None, router=None):
        self.root_path = Path(root_path or ".")
        self.router = router
        self.queued = queue.Queue()
        self.events = []
        self._premium_event_lock = threading.Lock()

    def _queue_ui(self, *event):
        self.queued.put(event)

    def _publish_premium_event(self, kind, payload):
        self.events.append((kind, payload))


def test_brain_setup_is_embedded_and_does_not_queue_hidden_tk_modal():
    app = FakeApp()
    assert PremiumUIBridge(app).open_native_panel("brain") == {
        "ok": True, "panel": "brain", "mode": "embedded"
    }
    assert app.queued.empty()


def test_mini_bridge_queues_minimize_and_existing_brain_surface():
    app = FakeApp()
    bridge = PremiumUIBridge(app)
    assert bridge.minimize_to_mini()["ok"] is True
    assert app.queued.get_nowait() == ("premium_minimize_to_mini", None)
    assert bridge.open_native_panel("updates")["ok"] is True
    assert app.queued.get_nowait() == ("premium_native_panel", "updates")


def test_gemini_setup_status_and_local_save_never_return_the_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("ALICE_RUNTIME_MODE", raising=False)

    class Router:
        gemini_model = "gemini-3.8-flash"

        def reload_config(self):
            self.gemini_model = "gemini-3.8-flash"

        def available(self):
            from os import environ
            return {"gemini": bool(environ.get("GEMINI_API_KEY"))}

    app = FakeApp(tmp_path, Router())
    bridge = PremiumUIBridge(app)
    assert bridge.gemini_setup_status() == {
        "ok": True, "configured": False, "model": "gemini-3.8-flash",
        "primary_provider": "gemini"
    }
    key = "AIzaSy_TEST_KEY_THAT_IS_NOT_REAL_123456"
    result = bridge.save_gemini_settings(key, "gemini-3.8-flash")
    assert result["ok"] is True
    assert key not in repr(result)
    assert key in (tmp_path / ".env").read_text(encoding="utf-8")
    assert bridge.gemini_setup_status()["configured"] is True


def test_brain_setup_dialog_is_real_and_mini_idle_is_static():
    root = Path(__file__).parents[1]
    html = (root / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")
    app_source = (root / "ui" / "app.py").read_text(encoding="utf-8")
    assert 'id="brainSetupDialog"' in html
    assert "api.save_gemini_settings" in html
    assert "api.test_gemini_connection" in html
    assert "api.minimize_to_mini" in html
    assert 'self._orb_state not in {"listening","thinking","speaking"}' in app_source
    assert "self.root.after(170,self._animate_orb_bubble)" in app_source
    assert "normalize_dropped_paths(paths)" in app_source


def test_dropped_paths_are_deduplicated_and_nonexistent_paths_are_ignored(tmp_path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("no file content is read by this test", encoding="utf-8")
    folder_path = tmp_path / "folder"
    folder_path.mkdir()

    result = normalize_dropped_paths([str(file_path), str(file_path), str(folder_path), str(tmp_path / "missing")])

    assert result == [str(file_path.resolve()), str(folder_path.resolve())]


def test_flux_ui_has_visible_home_content_and_user_selectable_persistent_themes():
    html = (Path(__file__).parents[1] / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")
    assert 'id="coreTitle"' in html and 'id="wakeBtn"' in html
    assert ".core-content{display:flex!important;visibility:visible!important;opacity:1!important" in html
    assert 'id="fluxThemeSelect"' in html
    assert all(f'value="{theme}"' in html for theme in ("gt3", "midnight", "cyber"))
    assert "alice.ui.flux-theme" in html


def test_flux_ui_voice_pill_matches_approved_mic_composer_and_keeps_runtime_submit_bridge():
    html = (Path(__file__).parents[1] / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")
    assert 'id="voiceConsoleMic"' in html and 'id="voiceConsoleInput"' in html
    assert 'id="composerForm"' in html and "requestSubmit()" in html
    assert ".voice-console-mic{width:58px!important;height:58px!important" in html
    assert ".voice-console input{display:block!important;visibility:visible!important;opacity:1!important" in html


def test_flux_ui_panels_keep_close_controls_reachable_on_small_screens():
    html = (Path(__file__).parents[1] / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")
    assert 'id="closeDrawer"' in html and 'id="closeOrbitPanel"' in html
    assert ".drawer-head{position:sticky;top:0" in html
    assert "@media(max-width:600px)" in html and ".close-orbit-panel{right:12px!important;top:68px!important}" in html


def test_bottom_idle_mic_expands_to_compact_message_and_attachment_pill():
    root = Path(__file__).parents[1]
    html = (root / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")
    css = (root / "ui" / "assets" / "alice-native-orbital-ui.css").read_text(encoding="utf-8")
    assert 'id="voiceConsoleMic"' in html and 'id="voiceConsoleInput"' in html
    assert 'id="voiceConsoleAttach"' in html and 'id="voiceConsoleSend"' in html
    assert "function sendConsoleText()" in html and "openConsoleText()" in html
    assert ".composer-wrap,.voice-state-strip { display:none!important; }" in css
    assert ".voice-console.text-open" in css and "height:66px!important" in css
    assert '<div class="voice-console" id="voiceConsole" aria-label="ALICE command console"><div class="voice-state-strip" id="voiceStateStrip"' in html
    assert "bottom:calc(100% - 1px)!important" in css


def test_mini_alice_matches_reference_frosted_voice_pill_and_keeps_runtime_controls():
    source = (Path(__file__).parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert "width,height=560,320" in source
    assert 'text="ALICE"' in source and 'self._mini_status="READY"' in source
    assert "rounded_rectangle(panel,radius=radius,outline=(78,208,211,242)" in source
    assert 'self._mini_input.insert(0,"Message ALICE' in source
    assert 'text="＋ Attach"' in source and 'text="Send  ➤"' in source
    assert '"listening":"LISTENING"' in source
    assert 'canvas.tag_bind("mini_mic"' in source
    assert 'canvas.tag_bind("mini_stop"' in source
    assert 'self._mini_window.geometry(f"{width}x{height}+' in source
    assert 'canvas.bind("<Double-Button-1>",lambda _e:self._mini_toggle_text())' in source
    assert 'self._mini_input.focus_set()' in source
    assert 'self._mini_canvas.itemconfigure(self._mini_response_label,text=self._mini_transcript)' in source
    assert "draw.rounded_rectangle((1,5,31,27)" in source
    assert "Hold fn to talk" not in source
    assert "_tray_pointer_position" in source and "_mini_toggle_text" in source


def test_brain_setup_uses_a_visible_accessible_webview_overlay():
    html = (Path(__file__).parents[1] / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")
    assert 'id="brainSetupOverlay" hidden' in html
    assert 'id="brainSetupDialog" role="dialog" aria-modal="true"' in html
    assert 'id="geminiApiKey" type="password"' in html
    assert 'id="geminiModel" type="text"' in html
    assert 'id="brainSetupSave"' in html and 'id="brainSetupTest"' in html
    assert "brainSetupOverlay.hidden=false" in html
    assert "document.addEventListener('keydown',trapBrainSetupFocus)" in html
    assert ".brain-setup-overlay[hidden]{display:none!important}" in html
    assert "brainSetupDialog.showModal()" not in html
