from alice.evolution.proposals import ImprovementProposalLedger
from alice.evolution.engineering_bridge import ProposalEngineeringBridge
import pytest


def test_unapproved_proposal_cannot_enter_engineering(tmp_path):
    ledger = ImprovementProposalLedger(tmp_path)
    p = ledger.propose("planner", "timeout", "verified", "better retries")
    bridge = ProposalEngineeringBridge(ledger)
    with pytest.raises(PermissionError):
        bridge.prepare(p.proposal_id)


def test_approved_proposal_prepares_plan_without_editing(tmp_path):
    ledger = ImprovementProposalLedger(tmp_path)
    p = ledger.propose("planner", "timeout", "verified", "better retries")
    assert ledger.approve_for_engineering(p.proposal_id)
    bridge = ProposalEngineeringBridge(ledger)
    plan = bridge.prepare(p.proposal_id)
    assert plan.goal.name == "Improve planner"
    assert "candidate only" in plan.goal.constraints


def test_candidate_preflight_is_side_effect_free(tmp_path):
    ledger = ImprovementProposalLedger(tmp_path)
    p = ledger.propose("planner", "timeout", "verified", "better retries")
    ledger.approve_for_engineering(p.proposal_id)
    root = tmp_path / "project"
    root.mkdir()
    target = root / "alice" / "planner.py"
    target.parent.mkdir()
    target.write_text("def plan():\n    return 1\n", encoding="utf-8")
    bridge = ProposalEngineeringBridge(ledger)
    result = bridge.preflight_candidate(root, p.proposal_id, [{"path": "alice/planner.py", "content": "def plan():\n    return 2\n"}])
    assert result["candidate_only"] is True
    assert result["impact"]["syntax_ok"] is True
    assert target.read_text(encoding="utf-8") == "def plan():\n    return 1\n"
