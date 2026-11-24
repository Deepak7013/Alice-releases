
"""Persistent artifact workflow memory: stores reusable, non-secret preferences and recipes."""
from __future__ import annotations
import json, time, hashlib, re
from pathlib import Path

class ArtifactMemory:
    def __init__(self, root=None):
        base=Path(root or Path(__file__).resolve().parents[2])/"alice_workspace"
        self.path=base/"artifact_memory.json"; self.path.parent.mkdir(parents=True,exist_ok=True)
        self.data=self._load()
    def _load(self):
        try:
            d=json.loads(self.path.read_text(encoding="utf-8"))
            return d if isinstance(d,dict) else {"styles":{},"recipes":{},"history":[]}
        except Exception:return {"styles":{},"recipes":{},"history":[]}
    def _save(self):
        tmp=self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data,indent=2,ensure_ascii=False),encoding="utf-8"); tmp.replace(self.path)
    @staticmethod
    def _key(value):
        return hashlib.sha256(str(value).strip().lower().encode()).hexdigest()[:20]
    @staticmethod
    def _clean(value):
        if isinstance(value, (bool, int, float)) or value is None:
            return value
        if isinstance(value, (list, tuple)):
            return [ArtifactMemory._clean(v) for v in value][:100]
        if isinstance(value, dict):
            return {str(k): ArtifactMemory._clean(v) for k,v in list(value.items())[:100]}
        s=str(value)
        s=re.sub(r'(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+','[REDACTED]',s)
        return s[:2000]
    def remember_style(self, artifact_kind, profile):
        safe={str(k):self._clean(v) for k,v in dict(profile).items()}
        self.data.setdefault("styles",{})[str(artifact_kind).lower()]=safe; self._save(); return safe
    def get_style(self, artifact_kind):
        return self.data.get("styles",{}).get(str(artifact_kind).lower(),{})
    def remember_recipe(self, task, artifact_kind, recipe):
        key=self._key(f"{task}|{artifact_kind}")
        safe={str(k):self._clean(v) for k,v in dict(recipe).items()}
        self.data.setdefault("recipes",{})[key]={"task":self._clean(task),"kind":artifact_kind,"recipe":safe,"used":0,"updated":time.time()}
        self._save()
        return key
    @staticmethod
    def _tokens(value):
        return {t for t in re.findall(r"[a-z0-9]+", str(value).lower()) if len(t) > 1}

    def _recipe_item(self, task, artifact_kind):
        key=self._key(f"{task}|{artifact_kind}")
        return key, self.data.get("recipes",{}).get(key)

    def recall_recipe(self, task, artifact_kind):
        key,item=self._recipe_item(task,artifact_kind)
        if item:
            item["used"]=int(item.get("used",0))+1
            self._save()
            return item["recipe"]
        return None

    def recall_best_recipe(self, task, artifact_kind):
        """Recall the strongest successful exact/similar recipe without exposing secrets."""
        key,item=self._recipe_item(task,artifact_kind)
        if item and item.get("successes", 0) >= item.get("failures", 0):
            item["used"]=int(item.get("used",0))+1
            self._save()
            return {"recipe": item["recipe"], "similarity": 1.0, "source": "exact"}
        target=self._tokens(task)
        best=None
        for candidate in self.data.get("recipes",{}).values():
            if str(candidate.get("kind","")).lower()!=str(artifact_kind).lower():
                continue
            if not candidate.get("successes", 0):
                continue
            ct=self._tokens(candidate.get("task",""))
            if not target or not ct:
                continue
            score=len(target & ct)/len(target | ct)
            if best is None or score > best[0]:
                best=(score,candidate)
        if best and best[0] >= 0.35:
            candidate=best[1]
            candidate["used"]=int(candidate.get("used",0))+1
            self._save()
            return {"recipe": candidate["recipe"], "similarity": round(best[0],3), "source": "similar"}
        return None

    def learn_outcome(self, task, artifact_kind, recipe, success, verification=None):
        """Update a reusable recipe from an observed outcome; successful outcomes strengthen it."""
        key=self._key(f"{task}|{artifact_kind}")
        now=time.time()
        safe={str(k):self._clean(v) for k,v in dict(recipe).items()}
        item=self.data.setdefault("recipes",{}).get(key)
        if not item:
            item={"task":self._clean(task),"kind":str(artifact_kind).lower(),
                  "recipe":safe,"used":0,"successes":0,"failures":0,"updated":now}
        if success:
            item["recipe"]=safe
            item["successes"]=int(item.get("successes",0))+1
        else:
            item["failures"]=int(item.get("failures",0))+1
        if verification is not None:
            item["last_verification"]={str(k):self._clean(v) for k,v in dict(verification).items()}
        item["updated"]=now
        self.data.setdefault("recipes",{})[key]=item
        self._save()
        return item

    def successful_workflows(self, artifact_kind=None, limit=10):
        items=list(self.data.get("recipes",{}).values())
        if artifact_kind:
            items=[x for x in items if x.get("kind")==str(artifact_kind).lower()]
        items=[x for x in items if int(x.get("successes",0))>0]
        items.sort(key=lambda x:(int(x.get("successes",0)), float(x.get("updated",0))), reverse=True)
        return items[:max(0,int(limit))]
    def record(self, artifact_kind,title,recipe,success=True):
        self.data.setdefault("history",[]).append({"kind":artifact_kind,"title":self._clean(title),
            "recipe":{str(k):self._clean(v) for k,v in dict(recipe).items()},"success":bool(success),"time":time.time()})
        self.data["history"]=self.data["history"][-200:]; self._save()
    def recent(self,n=10): return self.data.get("history",[])[-n:]
