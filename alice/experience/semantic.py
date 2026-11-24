"""Local semantic-style retrieval for Alice experiences.

Uses TF-IDF plus a small domain-neutral synonym/canonicalization layer. No
network calls or external model are required. This is retrieval intelligence,
not authorization.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_GROUPS = [
    {"ppt","pptx","powerpoint","presentation","slides","slide"},
    {"word","doc","docx","document","report","essay"},
    {"excel","xlsx","spreadsheet","workbook","table"},
    {"build","create","make","generate","produce","construct"},
    {"fix","repair","debug","resolve","correct"},
    {"research","investigate","study","analyze","analysis"},
    {"phone","mobile","android","smartphone","device"},
    {"code","coding","program","software","development"},
    {"college","university","academic","course"},
]

_CANON = {term: sorted(group)[0] for group in _GROUPS for term in group}

def normalize(text: str) -> str:
    toks=re.findall(r"[a-z0-9]+", str(text).lower())
    stop={"a","an","the","of","to","for","in","on","with"}
    out=[]
    for t in toks:
        if t in stop:
            continue
        c=_CANON.get(t,t)
        if not out or out[-1] != c:
            out.append(c)
    return " ".join(out)

def _task(record):
    if hasattr(record, "task"):
        return str(record.task)
    if isinstance(record, dict):
        return str(record.get("task",""))
    return str(record)

@dataclass
class SemanticMatch:
    index: int
    similarity: float

class SemanticExperienceIndex:
    def __init__(self, records=None):
        self.records=list(records or [])
        self.vectorizer=None
        self.matrix=None
        self._rebuild()

    def _rebuild(self):
        corpus=[normalize(_task(r)) for r in self.records]
        if not corpus:
            self.vectorizer=None; self.matrix=None; return
        self.vectorizer=TfidfVectorizer(ngram_range=(1,2), lowercase=True)
        self.matrix=self.vectorizer.fit_transform(corpus)

    def add(self, record):
        self.records.append(record); self._rebuild()

    def search(self, task, limit=10, minimum=0.0):
        if not self.records or self.matrix is None:
            return []
        q=self.vectorizer.transform([normalize(task)])
        sims=cosine_similarity(q,self.matrix)[0]
        ranked=sorted(enumerate(sims),key=lambda x:x[1],reverse=True)
        return [SemanticMatch(i,round(float(s),4)) for i,s in ranked
                if float(s)>=float(minimum)][:max(0,int(limit))]

    def explain(self, task, index):
        if self.vectorizer is None: return {"similarity":0.0,"shared_terms":[]}
        q=normalize(task).split()
        r=normalize(_task(self.records[index])).split()
        shared=sorted(set(q)&set(r))
        sim = cosine_similarity(
            self.vectorizer.transform([normalize(task)]),
            self.matrix[index:index+1]
        )[0][0]
        return {"similarity":round(float(sim),4),"shared_terms":shared}
