"""Verify local planning stays compact without hiding relevant capabilities."""

import pytest

from alice.agent.planner import Planner
from alice.agent.tool_selection import select_tools
from alice.tools.registry import ToolRegistry


def broad_registry():
    tools = ToolRegistry()
    for index in range(80):
        tools.add(f"archive_item_{index:02d}", "Inspect one archived item", lambda: None)
    tools.add("open_app", "Open a Windows application by name", lambda name: name, "execute")
    tools.add("discover_apps", "Discover installed Windows applications by name", lambda query="", limit=30: [])
    tools.add("browser_open", "Open a website URL", lambda url: url, "external")
    tools.add("market_research", "Research current stock market information", lambda: None)
    tools.add("trading_backtest", "Backtest a stock trading strategy", lambda: None)
    tools.add("trading_scope", "Inspect support for stocks and futures; futures simulation unavailable", lambda: None)
    tools.add("acquire_knowledge", "Research public sources and save knowledge with provenance", lambda topic, max_sources=4: None)
    tools.add("search_knowledge", "Search saved project knowledge with provenance", lambda query, limit=8, trusted_only=False: None)
    tools.add("self_upgrade", "Upgrade ALICE's own source with rollback", lambda: None, "write")
    tools.add("battery_status", "Read current Windows battery level", lambda: None)
    tools.add("list_files", "List files in Alice workspace", lambda path=".": [])
    tools.add("read_file", "Read a workspace file", lambda path: "")
    tools.add("write_file", "Write a workspace file", lambda path, content: path, "write")
    tools.add("world_state", "Inspect the current local world state", lambda: None)
    return tools


def test_explicit_pc_command_keeps_its_tool_and_bounds_catalog():
    tools = broad_registry()
    selected = select_tools("Open the Spotify app on my PC", tools)
    assert "open_app" in selected
    assert "discover_apps" in selected
    assert "world_state" in selected
    assert len(selected) <= 16
    assert len(selected) < len(tools.tools) // 2
    from alice.brain.intent_router import IntentRouter
    assert IntentRouter.requested_app("Open Spotify on my PC") == "Spotify"


def test_multi_step_market_request_retains_research_and_backtest():
    selected = select_tools("Research a stock strategy and backtest it", broad_registry())
    assert {"market_research", "trading_backtest"} <= set(selected)


@pytest.mark.parametrize("prompt_text,expected", [
    ("Research battery technology online and show sources", "acquire_knowledge"),
    ("Search my saved project knowledge", "search_knowledge"),
    ("Improve your own source code", "self_upgrade"),
    ("What is my battery level?", "battery_status"),
    ("Open Spotify on my PC", "open_app"),
])
def test_relevant_tool_is_available_across_brain_tasks(prompt_text, expected):
    assert expected in select_tools(prompt_text, broad_registry())


def test_nonfinancial_research_does_not_show_market_research():
    selected = select_tools("Research battery technology online and show sources", broad_registry())
    assert "market_research" not in selected
    assert "battery_status" not in selected
    assert "world_state" not in selected


def test_saved_memory_search_does_not_offer_new_web_acquisition():
    selected=select_tools("Search my saved project knowledge for ALICE voice preferences",
                          broad_registry())
    assert "search_knowledge" in selected
    assert "acquire_knowledge" not in selected
    assert "world_state" not in selected


def test_futures_paper_request_exposes_scope_without_spot_backtest():
    selected = select_tools("Paper trade a futures strategy", broad_registry())
    assert "trading_scope" in selected
    assert "trading_backtest" not in selected
    assert "world_state" not in selected


def test_singleton_no_argument_read_plans_without_local_model():
    class NoModel:
        def ask_json(self,*_args,**_kwargs):
            raise AssertionError("singleton read should not invoke slow model planning")
    planner=Planner(NoModel(),broad_registry())
    plan=planner.plan("Paper trade a futures strategy")
    assert [step["tool"] for step in plan["steps"]]==["trading_scope"]
    assert plan["steps"][0]["args"]=={}


def test_battery_status_skips_unneeded_world_state_and_model_plan():
    tools=broad_registry()
    selected=select_tools("What is my current battery status?",tools)
    assert list(selected)==["battery_status"]
    class NoModel:
        def ask_json(self,*_args,**_kwargs):
            raise AssertionError("direct battery read should skip model planning")
    plan=Planner(NoModel(),tools).plan("What is my current battery status?")
    assert plan["steps"][0]["tool"]=="battery_status"


def test_workspace_file_listing_skips_unneeded_world_state_and_model_plan():
    tools=broad_registry()
    selected=select_tools("List the files in my ALICE workspace",tools)
    assert list(selected)==["list_files"]
    class NoModel:
        def ask_json(self,*_args,**_kwargs):
            raise AssertionError("workspace list is a singleton read and needs no model plan")
    plan=Planner(NoModel(),tools).plan("List the files in my ALICE workspace")
    assert plan["steps"]==[{
        "tool":"list_files","args":{},"risk":"read",
    }]


def test_explicit_saved_knowledge_query_is_extracted_without_local_model():
    class NoModel:
        def ask_json(self,*_args,**_kwargs):
            raise AssertionError("explicit saved-memory query should skip model planning")
    request="Search my saved project knowledge for ALICE voice preferences."
    plan=Planner(NoModel(),broad_registry()).plan(request)
    assert plan["steps"]==[{
        "tool":"search_knowledge",
        "args":{"query":"ALICE voice preferences"},
        "risk":"read",
    }]


def test_explicit_sourced_online_research_skips_local_model_but_only_proposes():
    calls=[]
    tools=broad_registry()
    tools.add("acquire_knowledge", "Research public sources and save knowledge with provenance",
              lambda topic, max_sources=4: calls.append(topic), "external")
    class NoModel:
        def ask_json(self,*_args,**_kwargs):
            raise AssertionError("explicit sourced research should skip model planning")
    request="Research battery technology online and show sources"
    plan=Planner(NoModel(),tools).plan(request)
    assert plan["steps"]==[{
        "tool":"acquire_knowledge",
        "args":{"topic":"battery technology"},
        "risk":"external",
    }]
    assert calls==[]


@pytest.mark.parametrize("prompt,expected", [
    ("Research battery technology online and show sources", "battery technology"),
    ("Please research South Asian speech recognition on the internet.",
     "South Asian speech recognition"),
    ("Research battery technology and cite sources", "battery technology"),
    ("Research battery technology and then backtest it", None),
    ("Research this", None),
])
def test_explicit_research_topic_parser_is_narrow(prompt,expected):
    assert Planner._explicit_research_topic(prompt)==expected


def test_explicit_workspace_file_read_skips_model_and_stays_inside_workspace():
    class NoModel:
        def ask_json(self,*_args,**_kwargs):
            raise AssertionError("explicit workspace file read should skip model planning")
    tools=broad_registry()
    request="Read the file notes/README.md from my ALICE workspace"
    assert list(select_tools(request,tools))==["read_file"]
    plan=Planner(NoModel(),tools).plan(request)
    assert plan["steps"]==[{
        "tool":"read_file","args":{"path":"notes/README.md"},"risk":"read",
    }]


@pytest.mark.parametrize("prompt",[
    "Read the file ../.env from my ALICE workspace",
    "Read the file C:\\Users\\deepa\\.env from my ALICE workspace",
    "Read this file",
])
def test_workspace_read_shortcut_rejects_unsafe_or_vague_paths(prompt):
    assert Planner._explicit_workspace_read_path(prompt) is None


def test_singleton_write_still_uses_local_model():
    class NoModel:
        def ask_json(self,*_args,**_kwargs):
            raise AssertionError("write plans must use the local planner")
    with pytest.raises(AssertionError,match="write plans"):
        Planner(NoModel(),broad_registry()).plan("Improve your own source code")


def test_self_upgrade_plan_does_not_add_unrelated_machine_state_read():
    selected=select_tools("Improve your own source code",broad_registry())
    assert "self_upgrade" in selected
    assert "world_state" not in selected


def test_ambiguous_request_preserves_full_catalog():
    tools = broad_registry()
    assert select_tools("Help me with something", tools) == tools.describe()


def test_clear_desktop_click_gets_only_verified_controls_and_grounding_reads():
    tools=broad_registry()
    tools.add("click","Raw coordinate click",lambda x,y:None,"execute")
    tools.add("double_click","Raw double click",lambda x,y:None,"execute")
    tools.add("type_text","Raw text entry",lambda text:None,"execute")
    tools.add("desktop_observe_actions","Read visible accessible actions",lambda:None,"read")
    tools.add("desktop_click_accessible","Click a unique accessible target and verify expected text",lambda name,expected_text:None,"execute")
    tools.add("desktop_click_verified","Click coordinates and verify expected text",lambda x,y,expected_text:None,"execute")
    tools.add("desktop_type_verified","Type into a verified empty focused control",lambda text:None,"execute")
    tools.add("screen_state","Read current visible screen state",lambda:None,"read")
    tools.add("take_screenshot","Capture current desktop",lambda:None,"read")
    tools.add("world_state","Read local state",lambda:None,"read")

    selected=select_tools("Click the Save button on my desktop",tools)

    assert "desktop_observe_actions" in selected
    assert "desktop_click_accessible" in selected
    assert "desktop_click_verified" in selected
    assert "screen_state" in selected
    assert not ({"click","double_click","type_text"} & set(selected))
    assert len(selected)<=8


def test_browser_click_request_does_not_get_misrouted_to_desktop_tools():
    tools=broad_registry()
    tools.add("browser_click_role","Click a browser button with expected state",lambda role,name,expected_text:None,"external")
    tools.add("browser_snapshot","Inspect current browser tab and foreground state",lambda:None,"read")
    tools.add("desktop_click_accessible","Click a desktop button and verify expected text",lambda name,expected_text:None,"execute")
    tools.add("screen_state","Read desktop state",lambda:None,"read")

    selected=select_tools("Click the Save button in my browser",tools)

    assert "browser_click_role" in selected
    assert "desktop_click_accessible" not in selected
    assert "browser_snapshot" in selected


def test_pc_app_open_excludes_browser_tools_from_prompt_catalog():
    tools=broad_registry()
    tools.add("browser_open","Open URL in browser",lambda url:None,"external")
    selected=select_tools("Open Ollama on my PC",tools)
    assert "discover_apps" in selected
    assert not any(name.startswith("browser_") for name in selected)


def test_url_only_browser_request_retains_browser_open_capability():
    tools=broad_registry()
    tools.add("browser_open","Open URL in browser",lambda url:None,"external")
    selected=select_tools("Open https://example.com",tools)
    assert "browser_open" in selected


def test_model_cannot_execute_an_unshown_registered_tool():
    tools = broad_registry()
    selected = select_tools("Research battery technology online", tools)
    assert "archive_item_00" not in selected

    class BadRouter:
        def ask_json(self, prompt, schema, **kwargs):
            assert len(prompt) < 11000
            assert "archive_item_00" not in schema["properties"]["steps"]["items"]["properties"]["tool"]["enum"]
            return {"goal": "open Spotify", "done": False,
                    "steps": [{"tool": "archive_item_00", "args": {}}]}

    with pytest.raises(ValueError, match="Unavailable tool"):
        Planner(BadRouter(), tools).plan("Research battery technology online")


def test_planner_sends_only_status_for_selected_capabilities():
    tools = broad_registry()

    class Capabilities:
        def inventory(self):
            raise AssertionError("full capability inventory would bloat the local prompt")

        def status(self, name):
            return {"status": "unverified", "configured": True,
                    "verified": False, "secret": "must not reach model"}

    class Router:
        def ask_json(self, prompt, schema, **kwargs):
            assert "must not reach model" not in prompt
            assert '"name":"discover_apps"' in prompt
            assert '"open_app"' not in prompt
            assert len(prompt) < 3200
            assert "brokerage orders" not in prompt
            assert "email_count_today" not in prompt
            return {"goal": "open Spotify", "done": False,
                    "steps": [{"tool": "discover_apps", "args": {"query": "Spotify"}}]}

    plan = Planner(Router(), tools, capabilities=Capabilities()).plan("Open the Spotify app")
    assert plan["steps"][0]["tool"] == "discover_apps"


def test_planner_keeps_relevant_domain_policy_only():
    assert "source URLs" in Planner._system_for({"market_research": {}})
    assert "brokerage orders" in Planner._system_for({"market_research": {}})
    assert "email_count_today" not in Planner._system_for({"market_research": {}})
    assert "do not invent citations" in Planner._system_for({"acquire_knowledge": {}})


def test_planner_rejects_missing_or_invented_tool_arguments():
    tools = broad_registry()
    tools.tools.pop("discover_apps")
    class Router:
        def __init__(self, args):
            self.args=args
        def ask_json(self, *_args, **_kwargs):
            return {"goal":"open Spotify","done":False,
                    "steps":[{"tool":"open_app","args":self.args}]}
    for args in ({}, {"query":"Spotify"}):
        with pytest.raises(ValueError,match="Invalid tool arguments"):
            Planner(Router(args),tools).plan("Open Spotify")


def test_single_tool_plan_schema_requires_its_arguments_and_caps_repeat_count():
    tools=ToolRegistry()
    tools.add("self_upgrade","Upgrade ALICE",lambda goal:None,"write")
    schema=Planner(None,tools)._schema(Planner(None,tools)._with_argument_names(
        tools.describe()))
    step=schema["properties"]["steps"]
    assert step["maxItems"]==1
    args=step["items"]["properties"]["args"]
    assert args["required"]==["goal"]


def test_planner_rejects_repeating_a_write_action():
    tools=ToolRegistry()
    tools.add("self_upgrade","Upgrade ALICE",lambda goal:None,"write")
    planner=Planner(None,tools)
    plan={"goal":"improve","done":False,"steps":[
        {"tool":"self_upgrade","args":{"goal":"Improve local planner"}},
        {"tool":"self_upgrade","args":{"goal":"Improve local planner"}}]}
    with pytest.raises(ValueError,match="Duplicate action tool"):
        planner._validate(plan)


def test_app_launch_requires_a_path_from_observed_discovery():
    tools=ToolRegistry()
    tools.add("discover_apps","Discover applications",lambda query="",limit=30:[])
    tools.add("open_app","Open an observed application",lambda command:None,"execute")
    path=r"C:\Program Files\Spotify\Spotify.exe"
    class Router:
        def __init__(self,tool,command=None):
            self.tool=tool;self.command=command
        def ask_json(self,_prompt,schema,**_kwargs):
            names=schema["properties"]["steps"]["items"]["properties"]["tool"]["enum"]
            assert self.tool in names
            assert ("open_app" not in names if self.tool=="discover_apps"
                    else "discover_apps" not in names)
            return {"goal":"open Spotify","done":False,"steps":[{
                "tool":self.tool,
                "args":{"command":self.command} if self.command else {"query":"Spotify"}}]}
    first=Planner(Router("discover_apps"),tools).plan("Open Spotify")
    assert [step["tool"] for step in first["steps"]] == ["discover_apps"]
    observed=[{"tool":"discover_apps","status":"observed",
               "result":{"ok":True,"apps":[{"name":"Spotify","kind":"exe","path":path}]}}]
    second=Planner(Router("open_app",path),tools).plan_with_observations(
        "Open Spotify",None,"Observed a matching installed app.",observed)
    assert second["steps"][0]["args"]["command"] == path
    unsafe=Planner(Router("open_app",r"C:\Windows\System32\cmd.exe"),tools).plan_with_observations(
        "Open Spotify",None,"Observed a matching installed app.",observed)
    assert unsafe["steps"][0]["args"]["command"] == path
    with pytest.raises(ValueError,match="not observed"):
        Planner(None,tools)._validate(
            {"goal":"Open Spotify","done":False,"steps":[{"tool":"open_app",
              "args":{"command":r"C:\Windows\System32\cmd.exe"}}]},
            app_paths={path})


def test_exact_app_request_uses_observations_without_local_model():
    tools=ToolRegistry()
    tools.add("discover_apps","Discover applications",lambda query="":[])
    tools.add("open_app","Open an observed application",lambda command:None,"execute")

    class NoModel:
        def ask_json(self,*_args,**_kwargs):
            raise AssertionError("exact app request should not wait for the local model")

    planner=Planner(NoModel(),tools)
    first=planner.plan("Open Ollama on my PC")
    assert first["steps"][0]["tool"]=="discover_apps"
    assert first["steps"][0]["args"]=={"query":"Ollama"}

    path=r"C:\Program Files\Ollama\ollama app.exe"
    observed=[{"tool":"discover_apps","status":"observed","result":{"ok":True,"apps":[
        {"name":"Ollama","kind":"shortcut","path":r"C:\Start Menu\Ollama.lnk",
         "launch_path":path}]}}]
    second=planner.plan_with_observations("Open Ollama on my PC",None,"",observed)
    assert second["steps"][0]["tool"]=="open_app"
    assert second["steps"][0]["args"]=={"command":path}
    for status in ("verified","attempted","failed_verification"):
        later=planner.plan_with_observations("Open Ollama on my PC",None,"",
            observed+[{"tool":"open_app","status":status,"result":{"ok":True}}])
        assert later["steps"]==[]
    failed_discovery=planner.plan_with_observations("Open Ollama on my PC",None,"",
        [{"tool":"discover_apps","status":"error","error_class":"DiscoveryUnavailable"}])
    assert failed_discovery["steps"]==[]


def test_shortcut_needs_an_observed_exe_target_before_launch():
    tools=ToolRegistry()
    tools.add("discover_apps","Discover applications",lambda query="":[])
    tools.add("open_app","Open observed application",lambda command:None,"execute")
    exe=r"C:\Apps\Ollama\ollama app.exe"
    shortcut=r"C:\Start Menu\Ollama.lnk"
    observed=[{"tool":"discover_apps","status":"observed","result":{"ok":True,"apps":[
        {"name":"Ollama","kind":"shortcut","path":shortcut,"launch_path":exe}]}}]
    planner=Planner(None,tools)
    assert planner._observed_app_paths(observed) == {exe}
    assert planner._observed_app_paths([{"tool":"discover_apps","status":"observed",
        "result":{"ok":True,"apps":[{"name":"Ollama","kind":"shortcut","path":shortcut}]}}]) == set()


def test_planner_schema_restricts_no_argument_tools_and_drops_null_optional_values():
    tools=broad_registry()
    class Router:
        def ask_json(self, _prompt, schema, **_kwargs):
            args_schema=schema["properties"]["steps"]["items"]["properties"]["args"]
            assert args_schema["additionalProperties"] is False
            assert "query" not in args_schema["properties"]
            return {"goal":"battery status","done":False,
                    "steps":[{"tool":"battery_status","args":{}}]}
    assert Planner(Router(),tools).plan("What is my battery level?")["steps"][0]["args"] == {}

    class MemoryRouter:
        def ask_json(self, _prompt, _schema, **_kwargs):
            return {"goal":"saved knowledge","done":False,
                    "steps":[{"tool":"search_knowledge",
                              "args":{"query":"ALICE voice","limit":None,"trusted_only":None}}]}
    plan=Planner(MemoryRouter(),tools).plan("Search my saved project knowledge")
    assert plan["steps"][0]["args"] == {"query":"ALICE voice"}


def test_repeated_read_is_dropped_until_an_action_changes_state():
    tools=broad_registry()
    planner=Planner(None,tools)
    same_read={"tool":"world_state","args":{}}
    plan={"goal":"inspect","done":False,"steps":[same_read,
          {"tool":"battery_status","args":{}},same_read]}
    assert [step["tool"] for step in planner._validate(plan)["steps"]] == [
        "world_state","battery_status"]
    plan["steps"]=[same_read,{"tool":"open_app","args":{"name":"Spotify"}},same_read]
    assert [step["tool"] for step in planner._validate(plan)["steps"]] == [
        "world_state","open_app","world_state"]


def test_repeated_app_discovery_with_a_different_limit_is_dropped():
    planner=Planner(None,broad_registry())
    plan={"goal":"find Spotify","done":False,"steps":[
        {"tool":"discover_apps","args":{"query":"Spotify"}},
        {"tool":"discover_apps","args":{"query":"Spotify","limit":1}},
        {"tool":"world_state","args":{}}]}
    assert [step["tool"] for step in planner._validate(plan)["steps"]] == [
        "discover_apps","world_state"]
