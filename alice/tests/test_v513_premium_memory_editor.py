from pathlib import Path
from types import SimpleNamespace

from alice.memory.store import MemoryStore
from alice.ui.premium_bridge import PremiumUIBridge


def _bridge(tmp_path):
    return PremiumUIBridge(SimpleNamespace(memory=MemoryStore(root=tmp_path)))


def test_bridge_lists_safe_active_structured_memories(tmp_path):
    bridge = _bridge(tmp_path)
    record = bridge.app.memory.manager.set(
        "response style", "Be concise", kind="preference", source="user")
    bridge.app.memory.manager.set("old", "inactive", kind="fact")
    bridge.app.memory.manager.forget("old", limit=1)

    result = bridge.list_memories()

    assert result["ok"] is True
    assert len(result["memories"]) == 1
    item = result["memories"][0]
    assert item["id"] == record.id[:12]
    assert item["key"] == "response style"
    assert item["value"] == "Be concise"
    assert "path" not in item
    assert "database" not in item


def test_bridge_correction_uses_selected_id_and_persists(tmp_path):
    bridge = _bridge(tmp_path)
    selected = bridge.app.memory.manager.set("style", "Verbose", kind="preference")
    other = bridge.app.memory.manager.set("project", "ALICE", kind="context")

    result = bridge.correct_memory(selected.id[:12], "Concise")

    assert result["ok"] is True
    restarted = MemoryStore(root=tmp_path).manager.list()
    assert [(item.key, item.value) for item in restarted] == [
        ("style", "Concise"), ("project", "ALICE")]
    corrected = next(item for item in restarted if item.key == "style")
    assert corrected.supersedes == selected.id
    assert other.id != corrected.id


def test_bridge_rejects_invalid_or_ambiguous_memory_ids(tmp_path):
    bridge = _bridge(tmp_path)
    bridge.app.memory.manager.set("first", "one")
    bridge.app.memory.manager.set("second", "two")
    bridge.app.memory.manager.set("stale id text", "abcdef12")

    assert bridge.correct_memory("style", "unsafe fuzzy correction")["ok"] is False
    assert bridge.correct_memory("1234", "changed")["ok"] is False
    assert bridge.correct_memory("abcdef12", "must not fuzzy-match")["ok"] is False
    assert bridge.forget_memory("abcdef12", confirmed=True)["ok"] is False
    assert len(MemoryStore(root=tmp_path).manager.list()) == 3


def test_bridge_forget_requires_confirmation_and_targets_one_record(tmp_path):
    bridge = _bridge(tmp_path)
    first = bridge.app.memory.manager.set("first", "one")
    second = bridge.app.memory.manager.set("second", "two")

    assert bridge.forget_memory(first.id[:12])["ok"] is False
    assert len(MemoryStore(root=tmp_path).manager.list()) == 2
    result = bridge.forget_memory(first.id[:12], confirmed=True)

    assert result == {"ok": True, "forgotten": 1, "id": first.id[:12]}
    active = MemoryStore(root=tmp_path).manager.list()
    assert [(item.id, item.key) for item in active] == [(second.id, "second")]


def test_memory_workspace_uses_safe_text_rendering_and_visible_controls():
    html = (Path(__file__).parents[1] / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")

    assert 'id="memoryWorkspace"' in html
    assert "api.list_memories()" in html
    assert "api.correct_memory(memory.id,editor.value)" in html
    assert "api.forget_memory(memory.id,true)" in html
    assert "window.confirm(`Forget this saved memory?" in html
    assert "title.textContent=memory.key" in html
    assert "value.textContent=memory.value" in html
    assert "innerHTML=memory" not in html
