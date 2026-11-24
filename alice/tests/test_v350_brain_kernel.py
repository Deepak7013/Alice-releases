from alice.cognitive.brain import BrainKernel
from alice.user_model import UserModel
from alice.learning import LearningStore
from alice.world.model import WorldModel
from alice.capabilities.manager import CapabilityManager


def make(tmp_path):
    u=UserModel(tmp_path/'user.json')
    l=LearningStore(tmp_path/'lessons.json')
    u.learn('preferred_editor','VS Code',verified=True)
    l.learn('provider_failure_rule','Use bounded retry and smaller budgets',verified=True)
    w=WorldModel(tmp_path)
    w.observe('pc','os','Windows',source='test',confidence=.9)
    c=CapabilityManager(tmp_path)
    c.register('demo_tool','demo')
    c.record_success('demo_tool')
    return BrainKernel(user_model=u,learning_store=l,world_model=w,capability_manager=c)


def test_brain_unifies_verified_knowledge_and_workspace(tmp_path):
    b=make(tmp_path)
    s=b.think('plan a coding task using preferred_editor')
    assert s.intent == 'planning'
    assert s.workspace_id
    assert s.candidate_plan is not None
    assert any(getattr(x,'key','')=='preferred_editor' for x in s.verified_knowledge)
    ws=b.workspace.get(s.workspace_id)
    assert any('preferred_editor' in x for x in ws['known_facts'])


def test_hypothetical_is_analysis_only_and_never_approval(tmp_path):
    b=make(tmp_path)
    s=b.think('Suppose a script tries to delete files outside quarantine. What would you do?')
    assert s.intent == 'hypothetical'
    assert s.analysis_only and s.no_execution
    assert not s.approval_required
    assert s.next_stage == 'analyze'


def test_action_becomes_authorize_stage_not_execute(tmp_path):
    b=make(tmp_path)
    s=b.think('open the browser and search for the project')
    assert s.intent == 'action'
    assert s.approval_required
    assert s.next_stage == 'authorize'


def test_capability_gap_is_visible_without_acquisition(tmp_path):
    b=make(tmp_path)
    s=b.think('build a website with browser automation')
    assert 'browser_automation' in s.capability_gaps
    assert 'browser_automation' not in s.available_capabilities
    assert s.next_stage == 'authorize'


def test_unrelated_tool_names_do_not_create_capability_gaps(tmp_path):
    b = make(tmp_path)
    b.capabilities.register('voice_diagnostics', 'Read voice diagnostics')
    b.capabilities.register('browser_snapshot', 'Read browser state')
    s = b.think('what time is it?', create_workspace=False)
    assert s.capability_gaps == []


def test_capability_terms_match_words_not_substrings(tmp_path):
    b = make(tmp_path)
    s = b.think('open invoice.pdf', create_workspace=False)
    assert 'voice_io' not in s.capability_gaps


def test_missing_relevant_capability_is_still_reported(tmp_path):
    b = make(tmp_path)
    s = b.think('research battery technology', create_workspace=False)
    assert 'web_research' in s.capability_gaps


def test_brain_state_is_jsonable(tmp_path):
    import json
    s=make(tmp_path).inspect('diagnose provider failure')
    raw=json.dumps(s,default=str)
    assert 'diagnostic' in raw
