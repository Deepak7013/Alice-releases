from alice.experience.global_store import GlobalExperienceStore
from alice.intelligence.embeddings import EmbeddingEngine
from alice.intelligence.transfer import IntelligentTransfer

def test_transfer_uses_capability_and_semantic_support(tmp_path):
    s=GlobalExperienceStore(tmp_path); s.record("create college powerpoint presentation","use academic slides",True,evidence={"verified":True,"quality":.9})
    t=IntelligentTransfer(s,EmbeddingEngine("tfidf"),threshold=.05)
    x=t.find("build a college slide deck",3)
    assert x and x[0].transferable and x[0].score>0
