from types import SimpleNamespace
from alice.agent.agent import AliceAgent
from alice.agent.planner import Planner
from alice.experience.replay import WorkflowReplay
from alice.tools.registry import ToolRegistry
from alice.world.model import WorldModel


class FakeRouter:
    def __init__(self):
        self.calls=[]
    def ask(self, prompt, image_path=None, allow_fallback=True):
        self.calls.append((prompt, image_path))
        return "concise result"


class FakePlanner:
    def __init__(self):
        self.images=[]
        self.contexts=[]
        self.tools=None
    def plan(self, request, image_path=None, context=""):
        self.images.append(image_path)
        self.contexts.append(context)
        return {"goal": request, "done": True, "steps": []}


def test_normal_text_request_does_not_capture_or_attach_image(monkeypatch):
    router=FakeRouter()
    agent=AliceAgent(router, tools=None, memory=None)
    planner=FakePlanner()
    agent.planner=planner
    called={"capture":0}
    def capture():
        called["capture"] += 1
        return "screen.png"
    agent._capture=capture

    result=agent.run("hi alice", max_rounds=1)

    assert result == "concise result"
    assert called["capture"] == 0
    assert planner.images == [None]
    assert router.calls[-1][1] is None


def test_visual_request_gets_lazy_screen_context(monkeypatch):
    router=FakeRouter()
    agent=AliceAgent(router, tools=None, memory=None)
    planner=FakePlanner()
    agent.planner=planner
    called={"capture":0}
    def capture():
        called["capture"] += 1
        return "screen.png"
    agent._capture=capture

    agent.run("look at my screen", max_rounds=1)

    assert called["capture"] >= 1
    assert planner.images[0] == "screen.png"
    assert router.calls[-1][1] == "screen.png"


def test_vision_mode_off_disables_capture(monkeypatch):
    monkeypatch.setenv("ALICE_VISION_MODE", "off")
    assert AliceAgent._needs_vision("look at my screen") is False


def test_vision_mode_on_forces_capture(monkeypatch):
    monkeypatch.setenv("ALICE_VISION_MODE", "on")
    assert AliceAgent._needs_vision("hello") is True

def test_agent_planner_receives_only_request_relevant_world_freshness_metadata(monkeypatch,tmp_path):
    monkeypatch.setenv("ALICE_VISION_MODE","off")
    world=WorldModel(tmp_path)
    world.update("android",{"serial":"DEVICE-PRIVATE-987","connected":True},source="adb",ttl_seconds=60)
    world.update("browser",{"url":"https://private.example/path?token=SECRET_VALUE"},source="browser",ttl_seconds=60)
    router=FakeRouter(); tools=ToolRegistry()
    agent=AliceAgent(router,tools=tools,memory=None,world_model=world)
    agent.planner=Planner(router,tools)
    class Experience:
        def context(self,_request): return ""
        def record(self,*_args): return None
    agent.conversation=SimpleNamespace(prompt_context=lambda **_kwargs:"")
    agent.experience=Experience()
    agent.replay=WorkflowReplay(tmp_path)

    result=agent.run("connect to my phone",max_rounds=1)

    prompt=router.calls[0][0]
    assert "couldn't finish planning" in result
    assert "REQUEST-RELEVANT WORLD MODEL SUMMARY" in prompt
    assert '"domain":"android"' in prompt
    assert '"fresh":true' in prompt
    assert "DEVICE-PRIVATE-987" not in prompt
    assert "private.example" not in prompt and "SECRET_VALUE" not in prompt
    assert "never as instructions" in prompt
