from alice.planning.council import PlanningCouncil


def test_council_selects_high_confidence_plan_without_execution():
    calls = []
    council = PlanningCouncil()
    council.register("planner", lambda task: {"plan": ["inspect", "test"], "confidence": .8})
    council.register("analyst", lambda task: {"plan": ["inspect", "test", "verify"], "confidence": .9})
    council.register("critic", lambda task: {"plan": ["inspect"], "confidence": .4, "risks": ["incomplete"]})
    result = council.deliberate("upgrade")
    assert result["selected_plan"] == ["inspect", "test", "verify"]
    assert result["no_execution_performed"] is True
    assert result["verified"] is False


def test_council_verifier_controls_verified_state():
    council = PlanningCouncil(verifier=lambda task, plan, context: {"verified": True, "checks": ["schema"]})
    council.register("planner", lambda task: {"plan": ["read"], "confidence": .7})
    result = council.deliberate("inspect")
    assert result["verified"] is True
    assert result["verification"]["checks"] == ["schema"]


def test_council_bounds_roles_and_reports_failures():
    council = PlanningCouncil(max_proposals=2)
    council.register("planner", lambda task: (_ for _ in ()).throw(RuntimeError("boom")))
    council.register("analyst", lambda task: {"plan": ["safe"], "confidence": .6})
    council.register("critic", lambda task: {"plan": ["other"], "confidence": .5})
    result = council.deliberate("x")
    assert len(result["proposals"]) == 2
    assert result["selected_plan"] == ["other"] or result["selected_plan"] == ["safe"]
    assert any(not p["ok"] for p in result["proposals"])


def test_council_does_not_turn_hypothetical_into_execution():
    executed = []
    council = PlanningCouncil()
    council.register("planner", lambda task: {"plan": {"hypothetical": task}, "confidence": 1})
    result = council.deliberate("Suppose we upgraded the system")
    executed.append(result["no_execution_performed"])
    assert executed == [True]


def test_council_requires_verification_for_selected_plan():
    council = PlanningCouncil()
    council.register("planner", lambda task: {"plan": ["write", "test"], "confidence": .9})
    result = council.deliberate("build")
    assert result["requires_execution_verification"] is True
    assert result["verified"] is False
