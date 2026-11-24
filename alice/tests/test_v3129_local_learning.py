from alice.memory.store import MemoryStore

def test_chat_learning_persists_and_retrieves_locally(tmp_path):
    m=MemoryStore(tmp_path)
    added=m.learn_from_chat("Remember that my ALICE project is called Gluttony and I prefer concise responses.")
    assert added >= 1
    m2=MemoryStore(tmp_path)
    context=m2.context_for("ALICE project Gluttony concise responses", limit=8)
    assert "Gluttony" in context

def test_memory_query_does_not_require_provider(tmp_path):
    m=MemoryStore(tmp_path)
    m.learn_from_chat("From now on, keep my ALICE upgrades backwards compatible.")
    answer=m.local_memory_answer("What do you remember?")
    assert answer and "backwards compatible" in answer

def test_credentials_are_not_learned(tmp_path):
    m=MemoryStore(tmp_path)
    assert m.learn_from_chat("Remember API_KEY=super-secret-value") == 0
    assert "super-secret-value" not in m.context_for("API key secret", limit=10)

def test_chat_outcome_is_persistent(tmp_path):
    m=MemoryStore(tmp_path)
    assert m.learn_outcome("fix updater manifest", "Verified that the manifest is required", "v3.12.9")
    m2=MemoryStore(tmp_path)
    assert "manifest" in m2.context_for("updater manifest", limit=10).lower()
