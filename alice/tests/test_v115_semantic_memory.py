from alice.experience.global_store import GlobalExperienceStore
from alice.experience.semantic import SemanticExperienceIndex, normalize
from alice.experience.semantic_retrieval import SemanticExperienceRetriever

def test_synonym_normalization():
    assert normalize("make a PowerPoint presentation") == normalize("create slides")

def test_semantic_retrieval_matches_related_terms(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("create university presentation", "academic_slide_workflow", True,
             evidence={"verified":True,"quality":1.0})
    r=SemanticExperienceRetriever(s).search("make college slides")
    assert r and r[0]["workflow"]=="academic_slide_workflow"

def test_unrelated_task_does_not_match(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("cook pasta", "kitchen_workflow", True, evidence={"verified":True})
    assert SemanticExperienceRetriever(s).search("compile android program")==[]

def test_explanation_contains_shared_terms(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("create college report", "report_workflow", True, evidence={"verified":True})
    r=SemanticExperienceRetriever(s).search("make university document")
    assert r and isinstance(r[0]["explanation"]["shared_terms"],list)
