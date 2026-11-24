from alice.learning.loop import UnifiedLearningLoop

def test_loop_prefers_direct_verified_experience(tmp_path):
    l=UnifiedLearningLoop(tmp_path)
    l.record_outcome("create college presentation","ppt_recipe",True,
                     evidence={"verified":True,"quality":1.0})
    d=l.decide("make college presentation")
    assert d.reusable and d.workflow=="ppt_recipe" and d.source in {"direct_experience","semantic_experience"}

def test_loop_can_transfer_experience(tmp_path):
    l=UnifiedLearningLoop(tmp_path)
    l.record_outcome("create academic report","structured_recipe",True)
    d=l.decide("create academic presentation")
    assert d.reusable and d.source in {"cross_domain_transfer","semantic_experience"}

def test_loop_is_conservative_without_evidence(tmp_path):
    l=UnifiedLearningLoop(tmp_path)
    d=l.decide("compile an unrelated kernel")
    assert not d.reusable and d.source=="none"

def test_outcome_recording_is_explicit(tmp_path):
    l=UnifiedLearningLoop(tmp_path)
    r=l.record_outcome("x","workflow",False)
    assert r["recorded"] and r["success"] is False
