from alice.experience.global_store import GlobalExperienceStore
from alice.intelligence.embeddings import EmbeddingEngine
from alice.intelligence.semantic_memory import NeuralSemanticMemory

def test_embedding_fallback_is_vectorized_and_provenanced():
    r=EmbeddingEngine("tfidf").encode(["make presentation","create slides"])
    assert r.backend=="tfidf" and r.dimension>0 and not r.neural and len(r.vectors)==2

def test_sentence_transformer_path_is_supported(monkeypatch):
    import sys, types, numpy as np
    class FakeModel:
        def __init__(self,name,local_files_only=False):
            self.name=name
            assert local_files_only is True
        def encode(self,texts,normalize_embeddings=True): return np.ones((len(texts),4))
    monkeypatch.setitem(sys.modules,"sentence_transformers",types.SimpleNamespace(SentenceTransformer=FakeModel))
    r=EmbeddingEngine("sentence_transformers").encode(["a","b"])
    assert r.neural and r.backend=="sentence_transformers" and r.dimension==4

def test_semantic_memory_retrieves_paraphrase(tmp_path):
    s=GlobalExperienceStore(tmp_path); s.record("create college powerpoint presentation","use academic slides",True,evidence={"verified":True,"quality":.9})
    m=NeuralSemanticMemory(s,EmbeddingEngine("tfidf"),minimum=.01)
    x=m.search("create a university slide deck",1)[0]
    assert x.experience.workflow=="use academic slides" and x.confidence>0
