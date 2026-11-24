
from alice.planning import Goal, GoalPlanner, PlanStatus

def test_research_goal_creates_evidence_then_summary():
    p=GoalPlanner().plan("Research the latest battery technology")
    assert p.status is PlanStatus.READY
    assert [s.step_id for s in p.steps]==["step_1","step_2"]
    assert p.steps[1].depends_on==["step_1"]
    assert all(not s.requires_approval for s in p.steps)

def test_build_goal_has_verify_step():
    p=GoalPlanner().plan("Build a small website for my project")
    assert [s.step_id for s in p.steps]==["step_1","step_2","step_3","step_4"]
    assert "verify" in p.steps[-1].action.lower()
    assert p.steps[-1].depends_on==["step_3"]

def test_device_goal_preserves_authorization_boundary():
    p=GoalPlanner().plan("Connect to my phone and control it")
    assert [s.consequence for s in p.steps]==["low","low","low","high","low"]
    assert "permissions" in p.steps[2].action.lower()
    assert p.steps[2].requires_approval is False
    assert "authorization" in p.steps[3].action.lower()

def test_high_consequence_is_approval_gated():
    p=GoalPlanner().plan("Send an email to my friend")
    assert any(s.requires_approval for s in p.steps)
    assert any(s.consequence=="high" for s in p.steps)

def test_explicit_chain_is_dependency_ordered():
    p=GoalPlanner().plan("Open the file -> edit the file -> save the file")
    assert p.steps[1].depends_on==["step_1"]
    assert p.steps[2].depends_on==["step_2"]

def test_empty_goal_rejected():
    try: GoalPlanner().plan(" ")
    except ValueError: return
    assert False

def test_unknown_dependency_validation():
    from alice.planning.models import Plan, PlanStep
    g=Goal("x")
    p=Plan("p",g,[PlanStep("a","x",["missing"])])
    try: p.validate()
    except ValueError as e:
        assert "unknown dependency" in str(e)
    else: assert False
