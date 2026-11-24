from types import SimpleNamespace

import pytest
from alice.agent.agent import AliceAgent
from alice.providers.router import Router


@pytest.fixture(autouse=True)
def use_explicit_local_mode(monkeypatch):
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")


def test_fast_local_chat_uses_installed_small_model_and_warm_keep_alive(monkeypatch):
    monkeypatch.setenv("ALICE_ENABLE_LOCAL_AI","1")
    monkeypatch.setenv("ALICE_LOCAL_FAST_MODEL","gemma3:1b")
    router=Router()
    monkeypatch.setattr(router,"local_status",lambda:{
        "reachable":True,"models":["gemma3:1b","llama3.2:latest"]})
    calls={}
    monkeypatch.setattr(router,"_openai_client",lambda *args:object())
    def fake_chat(client,model,prompt,image_path=None,max_tokens=None,keep_alive=None):
        calls.update(model=model,max_tokens=max_tokens,keep_alive=keep_alive)
        return "Hello there."
    monkeypatch.setattr(router,"_chat",fake_chat)

    assert router.ask_fast("hello",max_tokens=96)=="Hello there."
    assert calls=={"model":"gemma3:1b","max_tokens":96,"keep_alive":"20m"}


def test_fast_local_chat_falls_back_to_primary_when_small_model_missing(monkeypatch):
    monkeypatch.setenv("ALICE_ENABLE_LOCAL_AI","1")
    router=Router()
    monkeypatch.setattr(router,"local_status",lambda:{"reachable":True,"models":[]})
    monkeypatch.setattr(router,"ask",lambda *args,**kwargs:"primary answer")
    assert router.ask_fast("hello",max_tokens=96)=="primary answer"


def test_fast_local_chat_falls_back_to_primary_on_empty_or_failed_result(monkeypatch):
    monkeypatch.setenv("ALICE_ENABLE_LOCAL_AI","1")
    router=Router()
    monkeypatch.setattr(router,"local_status",lambda:{"reachable":True,"models":["gemma3:1b"]})
    monkeypatch.setattr(router,"_openai_client",lambda *args:object())
    monkeypatch.setattr(router,"_chat",lambda *args,**kwargs:"")
    monkeypatch.setattr(router,"ask",lambda *args,**kwargs:"primary answer")
    assert router.ask_fast("hello",max_tokens=96)=="primary answer"


def test_fast_chat_stream_uses_small_local_model_when_installed(monkeypatch):
    monkeypatch.setenv("ALICE_ENABLE_LOCAL_AI","1")
    monkeypatch.setenv("ALICE_LOCAL_FAST_MODEL","gemma3:1b")
    router=Router()
    monkeypatch.setattr(router,"local_status",lambda:{"reachable":True,"models":["gemma3:1b"]})
    calls={}
    def fake_stream(provider,prompt,image_path,max_tokens,cancel_event,model_name=None):
        calls.update(provider=provider,model=model_name,max_tokens=max_tokens)
        yield "Hi"
        yield " there."
    monkeypatch.setattr(router,"_stream_openai_compatible",fake_stream)
    assert list(router.ask_fast_stream("hello",max_tokens=96))==["Hi"," there."]
    assert calls=={"provider":"local","model":"gemma3:1b","max_tokens":96}


def test_fast_chat_stream_falls_back_when_small_model_is_unavailable(monkeypatch):
    monkeypatch.setenv("ALICE_ENABLE_LOCAL_AI","1")
    router=Router()
    monkeypatch.setattr(router,"local_status",lambda:{"reachable":True,"models":[]})
    monkeypatch.setattr(router,"ask_stream",lambda *args,**kwargs:iter(["primary"]))
    assert list(router.ask_fast_stream("hello",max_tokens=96))==["primary"]


def test_fast_routes_never_send_images_to_small_text_model(monkeypatch):
    monkeypatch.setenv("ALICE_ENABLE_LOCAL_AI","1")
    router=Router()
    monkeypatch.setattr(router,"ask_vision",lambda prompt,image_path,max_tokens=None:
                        f"vision:{image_path}")
    monkeypatch.setattr(router,"_chat",lambda *args,**kwargs:
                        (_ for _ in ()).throw(AssertionError("text model received image")))
    assert router.ask_fast("describe",image_path="screen.png")=="vision:screen.png"
    assert list(router.ask_fast_stream("describe",image_path="screen.png"))==["vision:screen.png"]


def test_only_short_simple_conversation_uses_the_fast_route():
    check=AliceAgent._is_fast_chat_request
    assert check("hello Alice")
    assert not check("what time is it")
    assert not check("what is the weather today")
    assert not check("Explain why we need to verify desktop actions")
    assert not check("Compare these strategies and recommend the best one")
    assert not check("Tell me how to research this topic online")
    assert not check("write code that opens my browser and searches for a page")


def test_chat_uses_fast_model_only_for_short_simple_prompts():
    class Memory:
        def baseline(self): return ""
        def context_for(self,*args,**kwargs): return ""
    class RouterStub:
        def __init__(self): self.routes=[]
        def ask_fast(self,*args,**kwargs): self.routes.append("fast"); return "quick"
        def ask(self,*args,**kwargs): self.routes.append("primary"); return "careful"
    agent=AliceAgent.__new__(AliceAgent)
    agent.router=RouterStub(); agent.memory=Memory(); agent.knowledge_acquirer=None
    agent._brain_context=lambda _request:""

    assert agent.respond_text("define RAM briefly")=="quick"
    assert agent.respond_text("Explain how independent verification works")=="careful"
    assert agent.router.routes==["fast","primary"]


def test_streaming_chat_uses_fast_stream_for_simple_prompt():
    class Memory:
        def baseline(self): return ""
        def context_for(self,*args,**kwargs): return ""
    class RouterStub:
        def __init__(self): self.routes=[]
        def ask_fast_stream(self,*args,**kwargs):
            assert kwargs["max_tokens"]==48
            self.routes.append("fast"); yield "quick"
        def ask_stream(self,*args,**kwargs): self.routes.append("primary"); yield "careful"
    agent=AliceAgent.__new__(AliceAgent)
    agent.router=RouterStub(); agent.memory=Memory(); agent.knowledge_acquirer=None
    agent._brain_context=lambda _request:""

    assert list(agent.respond_text_stream("define RAM briefly"))==["quick"]
    assert list(agent.respond_text_stream("Explain how verification works"))==["careful"]
    assert agent.router.routes==["fast","primary"]


def test_exact_greetings_are_instant_and_skip_model_routing():
    agent=AliceAgent.__new__(AliceAgent)
    agent.router=object()
    assert agent.respond_text("hello Alice")=="Hello! I'm here. What can I help you with?"
    assert list(agent.respond_text_stream("thanks"))==["You're welcome!"]


def test_fast_chat_prompt_stays_small_and_keeps_only_bounded_context():
    prompt=AliceAgent._fast_chat_prompt(
        "define RAM briefly",
        "m"*2000,
        "h"*3000,
    )
    assert len(prompt)<1500
    assert "m"*501 not in prompt
    assert "h"*801 not in prompt
    assert "User: define RAM briefly" in prompt


def test_fast_chat_caps_generated_tokens():
    class Memory:
        def baseline(self): return ""
        def context_for(self,*args,**kwargs): return ""
    class RouterStub:
        def ask_fast(self,*args,**kwargs):
            assert kwargs["max_tokens"]==48
            return "quick"
        def ask(self,*args,**kwargs): raise AssertionError("simple chat must use the fast route")
    agent=AliceAgent.__new__(AliceAgent)
    agent.router=RouterStub(); agent.memory=Memory(); agent.knowledge_acquirer=None
    agent._brain_context=lambda _request:""
    assert agent.respond_text("define RAM briefly")=="quick"


def test_fast_chat_skips_unused_baseline_and_research_retrieval():
    class Memory:
        def baseline(self): raise AssertionError("fast chat must not build full baseline")
        def context_for(self,*args,**kwargs): return "short relevant preference"
    class Knowledge:
        def search(self,*args,**kwargs): raise AssertionError("fast chat must not run research retrieval")
    class RouterStub:
        def ask_fast(self,prompt,**kwargs):
            assert "short relevant preference" in prompt
            return "quick"
        def ask_fast_stream(self,prompt,**kwargs):
            assert "short relevant preference" in prompt
            yield "quick"
        def ask(self,*args,**kwargs): raise AssertionError("simple chat must use the fast route")
    agent=AliceAgent.__new__(AliceAgent)
    agent.router=RouterStub(); agent.memory=Memory(); agent.knowledge_acquirer=Knowledge()
    agent._brain_context=lambda _request:""
    assert agent.respond_text("define RAM briefly")=="quick"
    assert list(agent.respond_text_stream("define RAM briefly"))==["quick"]


def test_local_chat_request_carries_keep_alive_to_ollama():
    router=Router()
    captured={}
    class Completions:
        def create(self,**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
    client=SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    assert router._chat(client,"gemma3:1b","hello",max_tokens=24,keep_alive="20m")=="ok"
    assert captured["extra_body"]=={"keep_alive":"20m"}


def test_fast_model_defaults_to_installed_tiny_gemma(monkeypatch):
    monkeypatch.delenv("ALICE_LOCAL_FAST_MODEL",raising=False)
    assert Router().local_fast_model=="gemma3:270m"


def test_fast_chat_output_budget_is_short_bounded_and_configurable(monkeypatch):
    monkeypatch.delenv("ALICE_FAST_CHAT_MAX_OUTPUT_TOKENS",raising=False)
    assert AliceAgent._fast_chat_output_budget()==48
    monkeypatch.setenv("ALICE_FAST_CHAT_MAX_OUTPUT_TOKENS","64")
    assert AliceAgent._fast_chat_output_budget()==64
    monkeypatch.setenv("ALICE_FAST_CHAT_MAX_OUTPUT_TOKENS","900")
    assert AliceAgent._fast_chat_output_budget()==80
