
from alice.experience.global_store import GlobalExperienceStore
from alice.experience.retrieval import ExperienceRetriever
from alice.experience.optimizer import WorkflowOptimizer

def test_optimizer_selects_verified_workflow(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("make project report","research_write_verify",True,
             evidence={"verified":True,"quality":1})
    o=WorkflowOptimizer(ExperienceRetriever(s)).choose("make project report")
    assert o.selected=="research_write_verify" and o.confidence>0.55

def test_optimizer_can_decline_weak_match(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("make project report","old",True,evidence={})
    o=WorkflowOptimizer(ExperienceRetriever(s),confidence_floor=.99).choose("make project report")
    assert o.selected is None
