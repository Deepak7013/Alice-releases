"""An observed Start Menu shortcut can lead to one verified executable target."""

import os

import pytest

from alice.brain.intent_router import IntentRouter
from alice.agent.agent import AliceAgent
from alice.agent.planner import Planner
from alice.agent.executor import Executor
from alice.computer.discovery import AppDiscovery
from alice.computer.postconditions import verify_open_app_postcondition
from alice.execution.postconditions import PostconditionRegistry
from alice.safety.policy import SafetyPolicy
from alice.tools.registry import ToolRegistry


class _NoWeb:
    pass


def test_matching_shortcuts_resolve_to_one_executable(tmp_path):
    executable=tmp_path / "Ollama.exe"
    executable.write_bytes(b"test executable placeholder")
    first=tmp_path / "Ollama.lnk"
    second=tmp_path / "Ollama again.lnk"
    first.write_bytes(b"shortcut placeholder")
    second.write_bytes(b"shortcut placeholder")

    class Discovery(AppDiscovery):
        def _start_apps(self):
            return [
                {"name":"Ollama","path":str(first),"kind":"shortcut"},
                {"name":"Ollama","path":str(second),"kind":"shortcut"},
            ]

        def resolve_shortcut(self, path):
            return str(executable) if str(path) in {str(first),str(second)} else None

    discovery=Discovery()
    entries=discovery.search("Ollama")["apps"]
    assert all(row["launch_path"] == str(executable) for row in entries)
    assert IntentRouter(discovery,_NoWeb()).resolve_app("Ollama") == {
        "status":"exact","name":"Ollama","path":str(executable)}


def test_shortcut_without_safe_target_cannot_be_launched(tmp_path):
    shortcut=tmp_path / "Ollama.lnk"
    shortcut.write_bytes(b"shortcut placeholder")

    class Discovery(AppDiscovery):
        def _start_apps(self):
            return [{"name":"Ollama","path":str(shortcut),"kind":"shortcut"}]

        def resolve_shortcut(self, _path):
            return None

    discovery=Discovery()
    assert "launch_path" not in discovery.search("Ollama")["apps"][0]
    assert IntentRouter(discovery,_NoWeb()).resolve_app("Ollama")["status"] == "not_found"


@pytest.mark.skipif(os.name != "nt", reason="Windows shortcut COM only")
def test_shortcut_with_extra_arguments_is_not_promoted_to_an_executable(tmp_path, monkeypatch):
    import comtypes
    import comtypes.client

    shortcut=tmp_path / "Ollama.lnk"
    executable=tmp_path / "Ollama.exe"
    shortcut.write_bytes(b"shortcut placeholder")
    executable.write_bytes(b"executable placeholder")

    class Link:
        TargetPath=str(executable)
        Arguments="--unobserved-option"

    class Shell:
        def CreateShortcut(self, _path):
            return Link()

    monkeypatch.setattr(comtypes,"CoInitialize",lambda:None)
    monkeypatch.setattr(comtypes,"CoUninitialize",lambda:None)
    monkeypatch.setattr(comtypes.client,"CreateObject",lambda *_args,**_kwargs:Shell())
    assert AppDiscovery.resolve_shortcut(shortcut) is None
    Link.Arguments=""
    assert AppDiscovery.resolve_shortcut(shortcut)==str(executable.resolve())


def test_direct_app_route_reports_success_only_after_process_observation(tmp_path):
    executable=tmp_path / "Ollama.exe"
    executable.write_bytes(b"test executable placeholder")
    registry=ToolRegistry()
    registry.add("open_app","Open a Windows application",
                 lambda command:{"ok":True,"action":"open_app",
                                 "target":command,"pid":4567},"execute")
    postconditions=PostconditionRegistry()
    class Observer:
        processes=[]
        def process_by_pid(self,_pid):
            return {"ok":True,"processes":self.processes}
    observer=Observer()
    postconditions.register("open_app",
        lambda args,result:verify_open_app_postcondition(observer,args,result))
    agent=AliceAgent.__new__(AliceAgent)
    agent.policy=SafetyPolicy()
    agent.executor=Executor(registry,postconditions=postconditions)

    command=str(executable)
    unverified=agent.run_direct_tool_with_outcome("Open Ollama","open_app",
                                                   {"command":command})
    assert unverified["completion_state"]=="unverified"
    assert "couldn't verify" in unverified["summary"]

    observer.processes=[{"image":"Ollama.exe","pid":4567}]
    verified=agent.run_direct_tool_with_outcome("Open Ollama","open_app",
                                                 {"command":command})
    assert verified["completion_state"]=="verified"
    assert verified["verification_evidence"]["verified_actions"][0]["postcondition_ok"] is True


def test_fast_app_summary_requires_verified_launch_evidence():
    request="Open Ollama on my PC"
    discovery={"tool":"discover_apps","status":"observed","result":{
        "ok":True,"apps":[{"name":"Ollama","kind":"exe",
                           "path":r"C:\Program Files\Ollama\ollama app.exe"}]}}
    attempted={"tool":"open_app","status":"attempted","result":{"ok":True}}
    assert "couldn't verify" in AliceAgent._fast_app_summary(request,[discovery,attempted])
    verified={"tool":"open_app","status":"verified","result":{"ok":True},
              "postcondition":{"ok":True,"evidence":{"observed":True,"pid":1234}}}
    assert AliceAgent._fast_app_summary(request,[discovery,verified])=="Opened Ollama."
    invalid={**verified,"postcondition":{"ok":True,"evidence":{"observed":False}}}
    assert "couldn't verify" in AliceAgent._fast_app_summary(request,[discovery,invalid])


def test_agent_discovers_opens_and_verifies_without_model_round_trip():
    command=r"C:\Program Files\Ollama\ollama app.exe"
    calls=[]
    registry=ToolRegistry()
    registry.add("discover_apps","Discover applications",
                 lambda query="": {"ok":True,"apps":[{"name":"Ollama",
                     "kind":"exe","path":command}]})
    registry.add("open_app","Open observed application",
                 lambda command: calls.append(command) or {"ok":True,
                     "action":"open_app","target":command,"pid":7341},"execute")

    class NoModel:
        def ask_json(self,*_args,**_kwargs):
            raise AssertionError("no model call is needed for this exact app request")
        def ask(self,*_args,**_kwargs):
            raise AssertionError("no model call is needed for its observed outcome")

    class Observer:
        def process_by_pid(self,pid):
            return {"ok":True,"processes":[{"pid":pid,"image":"ollama app.exe"}]}

    class Store:
        def context(self,*_args,**_kwargs):
            return ""
        def record(self,*_args,**_kwargs):
            pass
        def candidate(self,*_args,**_kwargs):
            return None
        def prompt_context(self,*_args,**_kwargs):
            return ""

    postconditions=PostconditionRegistry()
    postconditions.register("open_app",
        lambda args,result:verify_open_app_postcondition(Observer(),args,result))
    agent=AliceAgent.__new__(AliceAgent)
    agent.router=NoModel()
    agent.planner=Planner(agent.router,registry)
    agent.executor=Executor(registry,postconditions=postconditions)
    agent.policy=SafetyPolicy()
    agent.experience=Store()
    agent.replay=Store()
    agent.conversation=Store()
    agent.memory=None
    agent.knowledge_acquirer=None
    agent.brain=None
    agent.world_model=None
    agent.capability_recovery=None
    agent.max_rounds=4
    outcome=agent.run_with_outcome("Open Ollama on my PC")
    assert calls==[command]
    assert outcome["summary"]=="Opened Ollama."
    assert outcome["completion_state"]=="verified"
    assert outcome["tool_sequence"]==["discover_apps","open_app"]


def test_local_planning_failure_stops_before_any_tool_execution():
    class FailingPlanner:
        def plan_with_observations(self,*_args,**_kwargs):
            raise TimeoutError("local model timeout")

    class NoExecutor:
        def run(self,*_args,**_kwargs):
            raise AssertionError("no tool may execute after planning fails")

    class NoModelSummary:
        def ask(self,*_args,**_kwargs):
            raise AssertionError("a failed local model cannot summarize itself")

    class Store:
        def context(self,*_args,**_kwargs):
            return ""
        def record(self,*_args,**_kwargs):
            pass
        def candidate(self,*_args,**_kwargs):
            return None
        def prompt_context(self,*_args,**_kwargs):
            return ""

    agent=AliceAgent.__new__(AliceAgent)
    agent.policy=SafetyPolicy()
    agent.planner=FailingPlanner()
    agent.executor=NoExecutor()
    agent.router=NoModelSummary()
    agent.experience=Store()
    agent.replay=Store()
    agent.conversation=Store()
    agent.memory=None
    agent.knowledge_acquirer=None
    agent.brain=None
    agent.world_model=None
    agent.capability_recovery=None
    agent.max_rounds=2
    outcome=agent.run_with_outcome("Plan a complex local task")
    assert outcome["completion_state"]=="unverified"
    assert "couldn't finish planning" in outcome["summary"]
    assert outcome["tool_sequence"]==["local_plan"]


@pytest.mark.parametrize("done",[False,True])
def test_empty_plan_without_evidence_cannot_be_reported_as_task_success(done):
    class EmptyPlanner:
        def __init__(self,done): self.done=done
        def plan_with_observations(self,*_args,**_kwargs):
            return {"goal":"create a report","done":self.done,"steps":[]}

    class NoExecutor:
        def run(self,*_args,**_kwargs):
            raise AssertionError("an empty plan must not execute tools")

    class OverconfidentModel:
        def ask(self,*_args,**_kwargs):
            return "The report was created successfully."

    class Store:
        def context(self,*_args,**_kwargs): return ""
        def record(self,*_args,**_kwargs): pass
        def candidate(self,*_args,**_kwargs): return None
        def prompt_context(self,*_args,**_kwargs): return ""

    agent=AliceAgent.__new__(AliceAgent)
    agent.policy=SafetyPolicy()
    agent.planner=EmptyPlanner(done)
    agent.executor=NoExecutor()
    agent.router=OverconfidentModel()
    agent.experience=Store()
    agent.replay=Store()
    agent.conversation=Store()
    agent.memory=None
    agent.knowledge_acquirer=None
    agent.brain=None
    agent.world_model=None
    agent.capability_recovery=None
    agent.max_rounds=2

    outcome=agent.run_with_outcome("Create a report")

    assert outcome["completion_state"]=="unverified"
    assert "couldn't finish planning" in outcome["summary"]
    assert "successfully" not in outcome["summary"].lower()
    assert outcome["tool_sequence"]==["local_plan"]


def test_round_limit_is_reported_incomplete_after_read_observation():
    class ContinuingPlanner:
        def plan_with_observations(self,*_args,**_kwargs):
            return {"goal":"inspect status","done":False,
                    "steps":[{"tool":"world_state","args":{}}]}

    class ReadExecutor:
        def run(self,plan):
            return [{"step":1,"tool":"world_state","status":"observed",
                     "result":{"ok":True,"state":"sample"}}]

    class OverconfidentModel:
        def ask(self,*_args,**_kwargs):
            return "The task is fully complete."

    class Store:
        def context(self,*_args,**_kwargs): return ""
        def record(self,*_args,**_kwargs): pass
        def candidate(self,*_args,**_kwargs): return None
        def prompt_context(self,*_args,**_kwargs): return ""

    agent=AliceAgent.__new__(AliceAgent)
    agent.policy=SafetyPolicy()
    agent.planner=ContinuingPlanner()
    agent.executor=ReadExecutor()
    agent.router=OverconfidentModel()
    agent.experience=Store()
    agent.replay=Store()
    agent.conversation=Store()
    agent.memory=None
    agent.knowledge_acquirer=None
    agent.brain=None
    agent.world_model=None
    agent.capability_recovery=None
    agent.max_rounds=1

    outcome=agent.run_with_outcome("Inspect system status")

    assert outcome["completion_state"]=="unverified"
    assert "couldn't finish planning" in outcome["summary"]
    assert "fully complete" not in outcome["summary"].lower()
    assert outcome["tool_sequence"]==["world_state","local_plan"]
