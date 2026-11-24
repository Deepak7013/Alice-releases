
from alice.experience.gateway import ExperienceGateway
from alice.planning.experience_planner import ExperienceAwarePlanner
from alice.planning.models import Goal

def test_experience_hint_is_added_without_changing_risk(tmp_path):
    g=ExperienceGateway(tmp_path)
    g.remember("send approved email","email_draft_review_send",True,evidence={"verified":True,"quality":1})
    p=ExperienceAwarePlanner(g).plan(Goal("send approved email"))
    assert any("Reusable workflow candidate" in x for x in p.assumptions)
    assert any(s.requires_approval for s in p.steps)

def test_no_experience_is_explicit(tmp_path):
    g=ExperienceGateway(tmp_path)
    p=ExperienceAwarePlanner(g).plan("make a report")
    assert any("No sufficiently reliable" in x for x in p.assumptions)
