from pathlib import Path
from alice.conversation.persistent import PersistentConversation
from alice.memory.store import MemoryStore
from alice.integrations.catalog import IntegrationCatalog
from alice.deployment.updater import InPlaceUpdater, is_protected


def test_conversation_survives_reopen(tmp_path):
    c=PersistentConversation(tmp_path)
    c.append("user","my name is Blue")
    c.append("assistant","Nice to meet you, Blue")
    c2=PersistentConversation(tmp_path)
    rows=c2.recent(10)
    assert [r["role"] for r in rows] == ["user","assistant"]
    assert "Blue" in rows[0]["content"]


def test_conversation_redacts_credentials(tmp_path):
    c=PersistentConversation(tmp_path)
    c.append("user","OPENROUTER_API_KEY=super-secret")
    assert "super-secret" not in c.recent(1)[0]["content"]


def test_conversation_redacts_spaced_gemini_key_and_unlabelled_google_key(tmp_path):
    c=PersistentConversation(tmp_path)
    key="AIzaSy" + "B" * 30
    c.append("user",f"Gemini API key={key}")
    assert key not in c.recent(1)[0]["content"]
    c.append("user",f"{key}")
    assert key not in c.recent(1)[0]["content"]


def test_memory_is_bounded(tmp_path):
    m=MemoryStore(tmp_path)
    for i in range(300):
        m.add(f"fact-{i}","fact")
    assert len(m.data["facts"]) == 200


def test_inplace_update_protects_env_and_state():
    assert is_protected(".env")
    assert is_protected("alice_workspace/history.jsonl")
    assert is_protected(".venv/Scripts/python.exe")


def test_integration_catalog_has_core_surfaces(tmp_path):
    c=IntegrationCatalog(tmp_path)
    names={x["name"] for x in c.list()}
    assert {"OpenRouter","Windows","Browser","Voice/TTS","Office artifacts"} <= names


def test_updater_snapshots_and_verifies_env(tmp_path):
    root=tmp_path/'install'; root.mkdir()
    (root/'alice').mkdir()
    (root/'VERSION.txt').write_text('ALICE v3.12.7',encoding='utf-8')
    env=root/'.env'; env.write_text('OPENROUTER_API_KEY=secret\n',encoding='utf-8')
    u=InPlaceUpdater(root)
    backup=u._backup_path()
    snap=u._snapshot_protected_state(backup)
    assert snap['env_exists'] is True
    assert (backup/'protected'/'.env').read_text(encoding='utf-8') == env.read_text(encoding='utf-8')
    u._verify_protected_state(snap)
    env.write_text('OPENROUTER_API_KEY=changed\n',encoding='utf-8')
    try:
        u._verify_protected_state(snap)
    except Exception as exc:
        assert 'protected .env' in str(exc).lower()
    else:
        raise AssertionError('changed .env was not detected')


def test_project_baseline_bootstraps_without_secrets(tmp_path):
    from alice.memory.project_baseline import ensure_baseline, read_baseline
    # Copy the package baseline into the temporary root to simulate a first run.
    src=Path('ALICE_PROJECT_BASELINE.md')
    (tmp_path/'ALICE_PROJECT_BASELINE.md').write_text(src.read_text(encoding='utf-8'),encoding='utf-8')
    out=ensure_baseline(tmp_path)
    assert out and out.exists()
    text=read_baseline(tmp_path)
    assert 'general-purpose local assistant' in text
    assert 'OPENROUTER_API_KEY' not in text


def test_agent_has_durable_conversation_context(tmp_path, monkeypatch):
    from alice.agent.agent import AliceAgent
    from alice.conversation.persistent import PersistentConversation
    class R: pass
    class T: pass
    # The constructor uses the real workspace by default, so patch the class
    # factory only for this structural contract test.
    monkeypatch.setattr('alice.agent.agent.PersistentConversation', lambda: PersistentConversation(tmp_path))
    a=AliceAgent(R(),T())
    a.conversation.append('user','remember this project detail')
    assert 'remember this project detail' in a.conversation.prompt_context()
