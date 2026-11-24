from alice.cognitive.core import CognitiveCore
from alice.memory.store import MemoryStore
from alice.world.model import WorldModel

class R:
    def available(self):
        return {"openrouter": True, "openai": False, "local": False}

class Runtime:
    scheduler=None
    approvals=object()

def test_local_first_memory_status_capabilities_and_diagnostics(tmp_path):
    m=MemoryStore(tmp_path)
    m.learn_from_chat("Remember that my ALICE project must preserve existing features.")
    c=CognitiveCore(m, Runtime(), R(), tmp_path)
    assert c.decide("What do you remember?").handled
    assert "preserve" in c.decide("What do you remember?").response
    assert "ALICE is online" in c.decide("status").response
    assert "persistent conversation" in c.decide("what can you do").response
    assert "memory=OK" in c.decide("self diagnostic").response

def test_normal_chat_is_not_falsely_handled(tmp_path):
    c=CognitiveCore(MemoryStore(tmp_path), Runtime(), R(), tmp_path)
    d=c.decide("Explain recursion simply")
    assert d.handled is False and d.needs_model is True

def test_basic_arithmetic_is_answered_locally_without_a_model():
    c=CognitiveCore()
    cases={
        "2 + 3":"5",
        "what is 19 * 19?":"361",
        "1.25 + 2.5":"3.75",
        "10 / 4":"2.5",
        "1 / 0":"Division by zero is undefined.",
    }
    for expression,expected in cases.items():
        result=c.decide(expression)
        assert result.handled and result.intent=="arithmetic"
        assert result.needs_model is False and result.response==expected

def test_arithmetic_parser_does_not_evaluate_general_text_or_expressions():
    c=CognitiveCore()
    for text in ("explain 2 + 3", "2 + 3 * 4", "open 2 + 3 website"):
        result=c.decide(text)
        assert result.handled is False and result.needs_model is True

def test_planning_attaches_bounded_world_observations_as_inert_context(tmp_path):
    world=WorldModel(tmp_path)
    world.update("android",{"connected_devices":["phone-1"]},source="adb",ttl_seconds=30)
    c=CognitiveCore(MemoryStore(tmp_path),Runtime(),R(),tmp_path,world_model=world)
    original=c.reasoning.plan
    captured={}
    def inspect(goal,*,context=None):
        captured["context"]=context
        return original(goal,context=context)
    c.reasoning.plan=inspect

    decision=c.decide("plan connect to my phone")

    assert decision.handled is True
    assert "Grounding: bounded WorldModel observations" in decision.response
    assert captured["context"]["world_model"]["trust"]=="observation_only"
    serialized=captured["context"]["world_model"]["context"]
    assert '"domain":"android"' in serialized
    assert '"fresh":true' in serialized
    assert "connected_devices" not in serialized
    assert "phone-1" not in serialized
    plan=original("connect to my phone",context=captured["context"])
    assert plan.goal.context["world_model"]["trust"]=="observation_only"
    assert any("observational context" in item for item in plan.assumptions)
    assert any("Refresh stale observations" in item for item in plan.unresolved)

def test_planning_without_world_model_remains_available(tmp_path):
    c=CognitiveCore(MemoryStore(tmp_path),Runtime(),R(),tmp_path)
    decision=c.decide("plan research offline agents")
    assert decision.handled and "Grounding:" not in decision.response

def test_live_application_injects_the_shared_world_model_into_cognitive_planning():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text(encoding="utf-8")
    assert "CognitiveCore(self.memory,self.runtime,self.router,world_model=self.world)" in source
    assert "knowledge_acquirer=self.knowledge_acquirer,world_model=self.world" in source
