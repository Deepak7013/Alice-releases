"""Pluggable neural embedding engine with safe local fallbacks.

Alice prefers a real embedding model when configured (SentenceTransformers or
an OpenAI-compatible embedding provider). TF-IDF remains available as a
fully-local deterministic fallback so the system never pretends an embedding
model exists when it does not.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import os
import numpy as np
from alice.providers.runtime_policy import RuntimePolicy

@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    backend: str
    model: str
    dimension: int
    neural: bool

class EmbeddingEngine:
    def __init__(self, backend="auto", model=None):
        self.backend=(backend or os.getenv("ALICE_EMBEDDING_BACKEND","auto")).lower()
        self.model_name=model or os.getenv("ALICE_EMBEDDING_MODEL","all-MiniLM-L6-v2")
        self._model=None
        self._tfidf=None

    def available_backends(self):
        out=[]
        try:
            import sentence_transformers  # noqa:F401
            out.append("sentence_transformers")
        except Exception: pass
        if RuntimePolicy.from_env().mode != "local_required" and os.getenv("OPENAI_API_KEY"):
            out.append("openai")
        out.append("tfidf")
        return out

    def _sentence_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            # Never let SentenceTransformers silently fetch weights from the Hub.
            # A cached model may still load; otherwise the caller gets the safe
            # deterministic TF-IDF fallback below.
            self._model=SentenceTransformer(self.model_name, local_files_only=True)
        return self._model

    def encode(self, texts: list[str]) -> EmbeddingResult:
        texts=[str(x) for x in texts]
        if not texts:
            return EmbeddingResult([],"none","",0,False)
        order=[]
        local_only = RuntimePolicy.from_env().mode == "local_required"
        if local_only:
            order = [self.backend] if self.backend in {"sentence_transformers", "tfidf"} else ["sentence_transformers", "tfidf"]
        elif self.backend != "auto": order=[self.backend]
        else: order=["sentence_transformers","openai","tfidf"]
        errors=[]
        for backend in order:
            try:
                if backend=="sentence_transformers":
                    model=self._sentence_model()
                    arr=np.asarray(model.encode(texts,normalize_embeddings=True),dtype=float)
                    return EmbeddingResult(arr.tolist(),backend,self.model_name,arr.shape[1],True)
                if backend=="openai":
                    from openai import OpenAI
                    client=OpenAI(api_key=os.environ["OPENAI_API_KEY"])
                    name=os.getenv("OPENAI_EMBEDDING_MODEL","text-embedding-3-small")
                    r=client.embeddings.create(model=name,input=texts)
                    arr=np.asarray([x.embedding for x in r.data],dtype=float)
                    norms=np.linalg.norm(arr,axis=1,keepdims=True); arr=arr/np.maximum(norms,1e-12)
                    return EmbeddingResult(arr.tolist(),backend,name,arr.shape[1],True)
                if backend=="tfidf":
                    from sklearn.feature_extraction.text import TfidfVectorizer
                    from sklearn.preprocessing import normalize
                    from alice.experience.semantic import normalize as alice_normalize
                    local_texts=[alice_normalize(x) for x in texts]
                    self._tfidf=TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True)
                    arr=normalize(self._tfidf.fit_transform(local_texts)).toarray()
                    return EmbeddingResult(arr.tolist(),backend,"tfidf",arr.shape[1],False)
            except Exception as exc:
                errors.append(f"{backend}:{type(exc).__name__}")
        raise RuntimeError("embedding backends failed: "+";".join(errors))

    @staticmethod
    def cosine(a,b):
        x=np.asarray(a,dtype=float); y=np.asarray(b,dtype=float)
        den=float(np.linalg.norm(x)*np.linalg.norm(y))
        return 0.0 if den<=1e-12 else float(np.dot(x,y)/den)
