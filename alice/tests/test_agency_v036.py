import tempfile
from pathlib import Path
from alice.agency import AgencyEngine, GoalStatus, Initiative


def test_goal_persists_and_reloads():
    with tempfile.TemporaryDirectory() as d:
        e=AgencyEngine(d)
        g=e.create_goal("Learn browser automation","Become better at web workflows",80)
        e2=AgencyEngine(d)
        assert e2.active_goals()[0]["id"] == g["id"]


def test_consequential_goal_requires_approval_recommendation():
    with tempfile.TemporaryDirectory() as d:
        e=AgencyEngine(d)
        g=e.create_goal("Send the report","Email the finished report to the client")
        decision=e.decide_for_goal(g["id"])
        assert decision["action"] == Initiative.RECOMMEND
        assert decision["requires_approval"] is True


def test_new_information_triggers_research_not_execution():
    with tempfile.TemporaryDirectory() as d:
        e=AgencyEngine(d)
        g=e.create_goal("Build an Android capability","Learn how to automate a new workflow")
        decisions=e.observe("new_information",{"source":"web"})
        d0=next(x for x in decisions if x["goal_id"]==g["id"])
        assert d0["action"] == Initiative.RESEARCH
        assert d0["requires_approval"] is False


def test_failed_task_triggers_replan():
    with tempfile.TemporaryDirectory() as d:
        e=AgencyEngine(d)
        g=e.create_goal("Finish project")
        decisions=e.observe("task_failed",{"error":"timeout"})
        d0=next(x for x in decisions if x["goal_id"]==g["id"])
        assert d0["action"] == Initiative.PLAN


def test_cancelled_goal_will_not_act():
    with tempfile.TemporaryDirectory() as d:
        e=AgencyEngine(d)
        g=e.create_goal("Do something")
        e.update_goal(g["id"],status=GoalStatus.CANCELLED)
        d0=e.decide_for_goal(g["id"],{"event":"deadline_approaching"})
        assert d0["action"] == Initiative.WAIT
