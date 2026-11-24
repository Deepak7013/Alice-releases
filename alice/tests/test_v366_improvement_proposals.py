from alice.evolution.proposals import ImprovementProposalLedger
def test_proposals_are_persistent_and_non_executing(tmp_path):
 l=ImprovementProposalLedger(tmp_path);p=l.propose('planner','repeated timeout','three verified failures','retry policy')
 assert p.status=='proposed';assert l.approve_for_engineering(p.proposal_id);assert l.list('engineering_review')[0]['proposal_id']==p.proposal_id
