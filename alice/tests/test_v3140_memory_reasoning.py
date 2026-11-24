from alice.memory.store import MemoryStore
from alice.reasoning.engine import ReasoningEngine
from alice.cognitive.core import CognitiveCore

class R:
    def council(self, prompt, image_path=None): return "council"

def test_structured_memory_learn_correct_forget(tmp_path):
    m=MemoryStore(tmp_path)
    assert m.learn_explicit("My preference is TradingView charts") == 1
    assert "TradingView" in m.structured_summary()
    corrected=m.correct("TradingView", "TradingView blue layout")
    assert corrected["ok"]
    assert "blue layout" in m.structured_summary()
    forgotten=m.forget("blue layout")
    assert forgotten["forgotten"] == 1
    assert "blue layout" not in m.structured_summary()

def test_reasoning_plan_and_verification(tmp_path):
    m=MemoryStore(tmp_path); r=ReasoningEngine(R(),m)
    plan=r.plan("research AI agents -> summarize findings")
    assert len(plan.steps)==2
    v=r.verify("research AI agents", "Here are the findings.", plan)
    assert v.ok and v.score > 0

def test_reasoning_rejects_conflicting_completion_claim(tmp_path):
    r=ReasoningEngine(memory=MemoryStore(tmp_path))
    v=r.verify("task", "Done, but I cannot verify the result.")
    assert not v.ok

def test_memory_controls_require_unique_match_and_support_exact_id(tmp_path):
    memory=MemoryStore(tmp_path)
    first=memory.manager.set("charts", "TradingView charts", kind="preference")
    second=memory.manager.set("alerts", "TradingView price alerts", kind="preference")
    core=CognitiveCore(memory=memory)

    ambiguous_forget=core.decide("forget memory TradingView")
    assert "nothing was deleted" in ambiguous_forget.response
    assert first.id[:8] in ambiguous_forget.response
    assert second.id[:8] in ambiguous_forget.response
    assert len(memory.manager.list("TradingView")) == 2

    ambiguous_correct=core.decide("correct memory TradingView => TradingView dark layout")
    assert "none was changed" in ambiguous_correct.response
    assert len(memory.manager.list("TradingView")) == 2

    exact=memory.forget(first.id[:8])
    assert exact["forgotten"] == 1
    assert len(memory.manager.list("TradingView")) == 1

def test_memory_query_lists_structured_preferences_with_editable_ids(tmp_path):
    from alice.cognitive import CognitiveCore as PackageCognitiveCore

    memory=MemoryStore(tmp_path)
    record=memory.manager.set("charts", "TradingView charts", kind="preference")
    answer=memory.local_memory_answer("what do you remember?")
    assert "TradingView charts" in answer
    assert record.id[:8] in answer
    assert PackageCognitiveCore is CognitiveCore

def test_memory_edits_and_forgetting_survive_store_restarts(tmp_path):
    first_store=MemoryStore(tmp_path)
    original=first_store.manager.set("market display", "Use compact charts", kind="preference")

    restarted=MemoryStore(tmp_path)
    assert original.id[:8] in restarted.local_memory_answer("what do you remember?")
    corrected=restarted.correct(original.id[:8], "Use compact charts with volume")
    assert corrected["ok"]

    after_correction=MemoryStore(tmp_path)
    active=after_correction.manager.list("market display")
    assert len(active) == 1
    assert active[0].value == "Use compact charts with volume"
    assert active[0].supersedes == original.id

    assert after_correction.forget(active[0].id[:8])["forgotten"] == 1
    after_forget=MemoryStore(tmp_path)
    assert after_forget.manager.list("market display") == []
