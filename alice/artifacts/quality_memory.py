
"""Stores verified quality outcomes so future artifact recipes favor stronger results."""
from __future__ import annotations
import json, time, hashlib
from pathlib import Path

class QualityMemory:
    def __init__(self,root=None):
        base=Path(root or Path(__file__).resolve().parents[2])/"alice_workspace"
        self.path=base/"artifact_quality_memory.json"; self.path.parent.mkdir(parents=True,exist_ok=True)
        self.data=self._load()
    def _load(self):
        try:
            d=json.loads(self.path.read_text())
            return d if isinstance(d,dict) else {}
        except Exception:return {}
    def _save(self):
        tmp=self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data,indent=2)); tmp.replace(self.path)
    @staticmethod
    def _key(task,kind,recipe):
        return hashlib.sha256(f"{task}|{kind}|{recipe}".lower().encode()).hexdigest()[:24]
    def record(self,task,kind,recipe,score,verified):
        key=self._key(task,kind,recipe)
        item=self.data.get(key,{"task":task,"kind":kind,"recipe":recipe,"samples":0,"mean_score":0.0})
        n=int(item["samples"]); item["mean_score"]=round((item["mean_score"]*n+float(score))/(n+1),4)
        item["samples"]=n+1; item["verified"]=bool(verified); item["updated"]=time.time()
        self.data[key]=item; self._save(); return item
    def best(self,task,kind,minimum_samples=1):
        items=[x for x in self.data.values() if x.get("kind")==kind and x.get("task")==task and x.get("samples",0)>=minimum_samples]
        return max(items,key=lambda x:(x.get("mean_score",0),x.get("samples",0)),default=None)
