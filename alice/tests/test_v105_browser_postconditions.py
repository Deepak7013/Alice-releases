from alice.agent.executor import Executor
from alice.browser.postconditions import (
    verify_browser_click_postcondition,
    verify_browser_fill_postcondition,
    verify_browser_new_tab_postcondition,
    verify_browser_open_postcondition,
    verify_browser_switch_tab_postcondition,
)
from alice.execution.postconditions import PostconditionRegistry
from alice.tools.registry import ToolRegistry


class BrowserState:
    def __init__(self):
        self.url="https://example.test/"
        self.tabs=[{"url":self.url}]
        self.value=""
        self.text=""

    def snapshot(self):
        return {"url":self.url,"tabs":[dict(row) for row in self.tabs]}

    def read_labeled_input(self,label):
        if label!="Message": raise LookupError(label)
        return self.value

    def page_text(self,max_chars=12000):
        return {"text":self.text[:max_chars],"url":self.url}


def test_browser_open_verifier_rereads_active_url_and_fails_closed_on_mismatch():
    browser=BrowserState()
    assert verify_browser_open_postcondition(browser,{"url":"https://example.test"},
        {"ok":True,"url":"https://example.test/"}).ok
    rejected=verify_browser_open_postcondition(browser,{"url":"https://other.test/"},
        {"ok":True,"url":"https://example.test/"})
    assert not rejected.ok
    assert rejected.evidence["observed"] is True


def test_browser_new_tab_requires_count_index_and_active_url_readback():
    browser=BrowserState()
    browser.url="https://second.test/"
    browser.tabs.append({"url":browser.url})
    result={"ok":True,"url":browser.url,"_postcondition_context":{"before_tab_count":1,"new_tab_index":1}}
    assert verify_browser_new_tab_postcondition(browser,{"url":"https://second.test"},result).ok
    browser.tabs[1]["url"]="https://other.test/"
    rejected=verify_browser_new_tab_postcondition(browser,{"url":"https://second.test"},result)
    assert not rejected.ok  # The saved new-tab index must refer to the new tab.


def test_browser_switch_verifier_confirms_selected_index_against_active_tab():
    browser=BrowserState(); browser.tabs.append({"url":"https://second.test/"})
    browser.url="https://second.test/"
    assert verify_browser_switch_tab_postcondition(browser,{"index":1},
        {"ok":True,"url":browser.url}).ok
    assert not verify_browser_switch_tab_postcondition(browser,{"index":0},
        {"ok":True,"url":browser.url}).ok


def test_browser_fill_executor_uses_dom_readback_and_never_returns_filled_secret():
    browser=BrowserState(); tools=ToolRegistry(); tools.postconditions=PostconditionRegistry()
    secret="private text must not appear in evidence"
    def fill(label,text):
        assert label=="Message"
        browser.value=text
        return {"ok":True}
    tools.add("browser_fill","Fill labeled browser input",fill,"external")
    tools.postconditions.register("browser_fill",lambda args,result:
        verify_browser_fill_postcondition(browser,args,result))

    result=Executor(tools).run({"steps":[{"tool":"browser_fill","args":{"label":"Message","text":secret}}]})[0]

    assert result["status"]=="verified"
    evidence=repr(result["postcondition"]["evidence"])
    assert secret not in evidence
    assert "value_sha256" in evidence


def test_browser_fill_fails_when_dom_readback_differs():
    browser=BrowserState()
    browser.value="different"
    result=verify_browser_fill_postcondition(browser,{"label":"Message","text":"wanted"},{"ok":True})
    assert not result.ok
    assert result.evidence["observed"] is True
    assert result.evidence["field_value_matches"] is False


def test_browser_click_observer_requires_declared_new_text_and_matching_readback():
    browser=BrowserState(); browser.text="Before"
    result={"ok":True,"url":browser.url,"_postcondition_context":{
        "kind":"text","before_url":browser.url,"expected_text_absent_before":True}}
    browser.text="Before\nSaved successfully"
    verified=verify_browser_click_postcondition(browser,{"expected_text":"Saved successfully"},result)
    assert verified.ok
    assert verified.evidence["expected_text_visible"] is True
    assert "Saved successfully" not in repr(verified.evidence)

    browser.text="Before"
    rejected=verify_browser_click_postcondition(browser,{"expected_text":"Saved successfully"},result)
    assert not rejected.ok


def test_browser_click_observer_requires_expected_url_transition_and_fresh_readback():
    browser=BrowserState()
    result={"ok":True,"url":"https://next.test/","_postcondition_context":{
        "kind":"url","before_url":"https://example.test/","expected_text_absent_before":True}}
    browser.url="https://next.test/"
    assert verify_browser_click_postcondition(browser,{"expected_url":"https://next.test"},result).ok
    browser.url="https://example.test/"
    assert not verify_browser_click_postcondition(browser,{"expected_url":"https://next.test"},result).ok


def test_browser_click_observer_rejects_missing_or_conflicting_expectations():
    browser=BrowserState()
    result={"ok":True,"url":browser.url,"_postcondition_context":{
        "kind":"text","before_url":browser.url,"expected_text_absent_before":True}}
    assert not verify_browser_click_postcondition(browser,{},result).ok
    assert not verify_browser_click_postcondition(browser,{
        "expected_text":"done","expected_url":"https://next.test"},result).ok


def test_browser_agent_click_requires_unique_target_and_observable_transition():
    from alice.browser.playwright_browser import BrowserAgent

    class Body:
        def __init__(self,page): self.page=page
        def inner_text(self,timeout=None): return self.page.text

    class Target:
        def __init__(self,page,count=1): self.page=page; self.matches=count
        def count(self): return self.matches
        def click(self,timeout=None): self.page.text+="\nSaved successfully"

    class Focus:
        def __init__(self,page): self.page=page
        def count(self): return 1
        def evaluate(self,_script): return self.page.focus_tag

    class Keyboard:
        def __init__(self,page): self.page=page
        def press(self,key): self.page.text+="\nSaved successfully"

    class Page:
        url="https://example.test/"
        text="Before"
        matches=1
        focus_tag="INPUT"
        def title(self): return "Test"
        def locator(self,selector): return Focus(self) if selector==":focus" else Body(self)
        def get_by_role(self,role,name,exact): return Target(self,self.matches)
        def get_by_text(self,text,exact): return Target(self,self.matches)

    class Context:
        def __init__(self,page): self.pages=[page]

    browser=BrowserAgent(); browser.page=Page(); browser.context=Context(browser.page)
    result=browser.click_role("button","Save",expected_text="Saved successfully")
    assert verify_browser_click_postcondition(browser,{
        "expected_text":"Saved successfully"},result).ok

    browser.page.text="Before"
    result=browser.click_text("Save",expected_text="Saved successfully")
    assert verify_browser_click_postcondition(browser,{
        "expected_text":"Saved successfully"},result).ok

    browser.page.text="Before"
    browser.page.keyboard=Keyboard(browser.page)
    result=browser.press("ENTER",expected_text="Saved successfully")
    assert verify_browser_click_postcondition(browser,{
        "expected_text":"Saved successfully"},result).ok

    browser.page.text="Before"
    browser.page.focus_tag="BODY"
    try:
        browser.press("ENTER",expected_text="Saved successfully")
    except ValueError as exc:
        assert "focused interactive" in str(exc)
    else:
        raise AssertionError("keypress without an interactive focus was accepted")
    browser.page.focus_tag="INPUT"

    browser.page.text="Before"
    tools=ToolRegistry(); tools.postconditions=PostconditionRegistry()
    tools.add("browser_click_role","Verified browser click",browser.click_role,"external")
    tools.postconditions.register("browser_click_role",lambda args,out:
        verify_browser_click_postcondition(browser,args,out))
    executed=Executor(tools).run({"steps":[{"tool":"browser_click_role","args":{
        "role":"button","name":"Save","expected_text":"Saved successfully"}}]})[0]
    assert executed["status"]=="verified"
    assert "_postcondition_context" not in executed["result"]
    assert "Saved successfully" not in repr(executed["postcondition"]["evidence"])

    browser.page.matches=2
    try:
        browser.click_role("button","Save",expected_text="Done")
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("ambiguous click target was accepted")

    try:
        browser.click_role("button","Save")
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("click without expected state was accepted")


def test_browser_click_postconditions_are_registered_in_active_app():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[2]/"alice"/"ui"/"app.py").read_text(encoding="utf-8")
    assert 't.postconditions.register("browser_click_role"' in source
    assert 't.postconditions.register("browser_click_text"' in source
    assert 't.postconditions.register("browser_press"' in source
