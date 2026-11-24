from alice.agent.agent import AliceAgent
import sqlite3
import pytest

class K:
    def search(self,query,limit=5):
        return [{"topic":"python","text":"Use list slicing to reverse a list.","confidence":.8,"source":{"locator":"https://example.com"}}]

def test_agent_can_retrieve_acquired_knowledge_context():
    a=AliceAgent.__new__(AliceAgent); a.knowledge_acquirer=K()
    x=a._knowledge_context('reverse python list')
    assert 'list slicing' in x and 'https://example.com' in x


def test_knowledge_and_memory_database_contexts_close_connections(tmp_path):
    from alice.knowledge.store import KnowledgeStore
    from alice.memory.manager import MemoryManager
    from alice.knowledge.models import SourceEvidence

    db_path=tmp_path / "alice_workspace" / "library" / "alice_knowledge.sqlite3"
    stores=(KnowledgeStore(db_path), MemoryManager(tmp_path))
    item=stores[0].create("topic", "persistent research", SourceEvidence(kind="document"))
    memory=stores[1].set("project", "persistent preference")
    assert KnowledgeStore(db_path).get(item.id).text == "persistent research"
    assert MemoryManager(tmp_path).list("project")[0].id == memory.id
    for store in stores:
        with store._connect() as connection:
            connection.execute("SELECT 1")
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
