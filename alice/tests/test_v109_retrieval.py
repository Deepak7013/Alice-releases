
from alice.experience.global_store import GlobalExperienceStore
from alice.experience.retrieval import ExperienceRetriever

def test_verified_evidence_ranks_higher(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("build presentation","weak",True,evidence={"verified":False,"quality":0.0})
    s.record("build presentation","strong",True,evidence={"verified":True,"quality":1.0})
    r=ExperienceRetriever(s).search("build presentation")
    assert r and r[0].workflow=="strong"

def test_low_similarity_is_filtered(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("cook pasta","cook",True,evidence={"verified":True})
    assert ExperienceRetriever(s).search("compile android app")==[]
