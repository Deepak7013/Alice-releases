from alice.evolution.proposals import ImprovementProposalLedger
from alice.evolution.proposal_bridge import ExperienceProposalBridge


def test_verified_failure_becomes_inert_proposal(tmp_path):
    ledger = ImprovementProposalLedger(tmp_path)
    bridge = ExperienceProposalBridge(ledger)
    p = bridge.observe_failure(
        request="open dashboard",
        tools=["browser"],
        summary="browser timeout",
        lessons=["retry with bounded backoff"],
    )
    assert p.status == "proposed"
    assert ledger.list("proposed")[0]["proposal_id"] == p.proposal_id


def test_repeated_same_observation_is_deduplicated(tmp_path):
    ledger = ImprovementProposalLedger(tmp_path)
    bridge = ExperienceProposalBridge(ledger)
    a = bridge.observe_failure(request="sync data", summary="timeout", lessons=["retry"])
    b = bridge.observe_failure(request="sync data", summary="timeout", lessons=["retry"])
    assert a.proposal_id == b.proposal_id
    assert len(ledger.list()) == 1


def test_bridge_cannot_auto_approve(tmp_path):
    ledger = ImprovementProposalLedger(tmp_path)
    bridge = ExperienceProposalBridge(ledger)
    p = bridge.observe_failure(request="build", summary="test failure")
    assert p.status == "proposed"
    assert ledger.list("engineering_review") == []


def test_rank_is_deterministic_and_inert(tmp_path):
    ledger = ImprovementProposalLedger(tmp_path)
    bridge = ExperienceProposalBridge(ledger)
    p1 = bridge.observe_failure(request="a", summary="one")
    p2 = bridge.observe_failure(request="b", summary="two")
    ranked = bridge.rank()
    assert {x["proposal_id"] for x in ranked} == {p1.proposal_id, p2.proposal_id}
    assert all(x["status"] == "proposed" for x in ranked)
