from datetime import datetime
from pathlib import Path
import threading

from alice.ui.app import AliceUI


def test_premium_activity_events_have_runtime_timestamp_and_monotonic_id():
    app = object.__new__(AliceUI)
    app._premium_event_lock = threading.Lock()
    app._premium_events = []
    app._premium_event_seq = 0

    app._publish_premium_event("runtime_ready", {"status": "ready"})
    app._publish_premium_event("message", {"speaker": "You", "text": "private text"})

    first, second = app._premium_events
    assert (first["id"], second["id"]) == (1, 2)
    assert first["type"] == "runtime_ready"
    assert first["data"] == {"status": "ready"}
    assert datetime.fromisoformat(first["timestamp"])
    assert datetime.fromisoformat(second["timestamp"])


def test_live_dashboard_activity_is_event_backed_and_does_not_render_chat_text():
    root = Path(__file__).resolve().parents[2]
    html = (root / "alice" / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")

    assert 'id="activityList"' in html
    assert 'id="activityEmpty"' in html
    assert 'id="notificationDialog"' in html
    assert 'Activity Center' in html
    assert 'Luca' not in html and 'luca' not in html
    assert "function addActivity(ev)" in html
    assert "addActivity(ev)" in html
    assert "new Date(ev.timestamp)" in html
    assert "Conversation controls connected" in html
    assert "The live conversation service is available." not in html
    assert "The runtime has not reported any activity yet." in html
    assert "Interface initialized" not in html
    assert "Conversation layer available" not in html
    assert "Ambient core online" not in html
    activity_renderer = html.split("function addActivity(ev)", 1)[1].split("$('#clearActivity')", 1)[0]
    assert "data.text" not in activity_renderer


def test_dashboard_reports_observed_runtime_bridge_instead_of_static_preview_claims():
    root = Path(__file__).resolve().parents[2]
    html = (root / "alice" / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")

    assert 'id="runtimeBridgeState"' in html
    assert "function setRuntimeBridge(connected,status)" in html
    assert "setRuntimeBridge(!!status,status)" in html
    assert "NOT CONNECTED" in html  # Only the live disconnected state, not a hard-coded claim.
    assert "This is ALICE's front-end preview" not in html
    assert "Real reasoning, memory, voice output" not in html


def test_premium_runtime_emits_only_observed_startup_activity():
    root = Path(__file__).resolve().parents[2]
    source = (root / "alice" / "ui" / "app.py").read_text(encoding="utf-8")

    assert 'app._publish_premium_event("runtime_ready"' in source
    assert 'app._publish_premium_event("conversation_ready"' in source
    assert 'app._publish_premium_event("ambient_core_online"' not in source
