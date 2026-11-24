import queue
import threading
from pathlib import Path

from alice.ui.premium_bridge import PremiumUIBridge


class FakeApp:
    def __init__(self):
        self.queued = queue.Queue()
        self._premium_event_lock = threading.Lock()
        self._premium_events = [{"id": 1, "type": "message", "data": {"speaker": "Alice", "text": "ready"}}]

    def _queue_ui(self, *event):
        self.queued.put(event)

    @staticmethod
    def _app_version():
        return "v4.110.0"

    @staticmethod
    def provider_status():
        return "Configured: openrouter"


def test_premium_bridge_submits_nonempty_chat_to_runtime_queue():
    app = FakeApp()
    bridge = PremiumUIBridge(app)

    assert bridge.send_message("  hello ALICE  ") == {"ok": True}
    assert app.queued.get_nowait() == ("premium_submit", "hello ALICE")


def test_premium_bridge_rejects_empty_and_oversized_messages():
    bridge = PremiumUIBridge(FakeApp())

    assert bridge.send_message("  ")["ok"] is False
    assert bridge.send_message("x" * 20_001)["ok"] is False


def test_premium_bridge_returns_only_new_runtime_events_and_safe_status():
    bridge = PremiumUIBridge(FakeApp())

    assert bridge.poll_events(0)[0]["id"] == 1
    assert bridge.poll_events(1) == []
    assert bridge.get_status() == {"version": "v4.110.0", "provider": "Configured: openrouter", "speak_mode": False}


def test_premium_bridge_opens_local_provider_setup_without_exposing_key():
    app = FakeApp()
    bridge = PremiumUIBridge(app)

    assert bridge.open_provider_setup() == {"ok": True}
    assert app.queued.empty()


def test_premium_bridge_rejects_hosted_key_without_persisting_or_queuing(tmp_path):
    app = FakeApp()
    app.root_path = Path(tmp_path)
    env = tmp_path / ".env"
    env.write_text("ALICE_RUNTIME_MODE=local_required\n", encoding="utf-8")
    bridge = PremiumUIBridge(app)

    result = bridge.save_provider_settings("sk-or-v1-test-only", "openrouter/auto", False)

    assert result["ok"] is False
    assert "local-only" in result["error"]
    assert "sk-or-v1-test-only" not in repr(result)
    assert env.read_text(encoding="utf-8") == "ALICE_RUNTIME_MODE=local_required\n"
    assert app.queued.empty()


def test_premium_bridge_rejects_preferences_without_existing_key(tmp_path):
    app = FakeApp()
    app.root_path = Path(tmp_path)
    app.router = type("Router", (), {"reload_config": lambda self: None})()
    app.provider_status = lambda: "none"

    result = PremiumUIBridge(app).save_provider_settings("", "openrouter/auto", False)

    assert result["ok"] is False
    assert "local-only" in result["error"]


def test_premium_bridge_routes_workspace_panels_through_runtime_queue():
    app = FakeApp()
    bridge = PremiumUIBridge(app)

    assert bridge.open_native_panel("updates") == {"ok": True}
    assert app.queued.get_nowait() == ("premium_native_panel", "updates")
    assert bridge.open_native_panel("arbitrary") == {"ok": False, "error": "Unknown workspace panel."}
    assert app.queued.empty()


def test_premium_bridge_queues_speak_mode_without_threading_tk_calls():
    app = FakeApp()
    bridge = PremiumUIBridge(app)

    assert bridge.set_speak_mode(True) == {"ok": True, "enabled": True}
    assert app.queued.get_nowait() == ("premium_speak_mode", True)
