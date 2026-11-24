"""Local persistent memory plus a durable SQLite knowledge library."""
import json, re, time
from pathlib import Path
from .project_baseline import ensure_baseline, read_baseline
from .learner import ChatLearningLibrary
from .manager import MemoryManager
from ..core.atomic_json import atomic_write_json

SECRET=re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]")
class MemoryStore:
    def __init__(self, root=None):
        root=Path(root or Path(__file__).resolve().parents[2])
        self.root=root
        ensure_baseline(root)
        self.path=root/"alice_workspace"/"memory.json"
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.data=self._load()
        self.library=ChatLearningLibrary(root)
        self.manager=MemoryManager(root)
    def _load(self):
        try:return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:return {"facts":[],"preferences":[],"tasks":[]}
    def _save(self):
        atomic_write_json(self.path, self.data)
    def add(self,text,kind="fact"):
        if SECRET.search(text): return False
        item={"text":str(text)[:1000],"time":time.time()}
        key=kind+"s"
        self.data.setdefault(key,[]).append(item); self.data[key]=self.data.get(key,[])[-200:]; self._save(); return True
    def learn_from_chat(self,text):
        return self.library.learn_user_turn(text)
    def learn_outcome(self,request,outcome,version=""):
        return self.library.learn_verified_outcome(request,outcome,version)
    def context_for(self,query,limit=6):
        return self.library.context_for(query,limit)
    def local_memory_answer(self,query):
        return self.library.local_memory_answer(query)
    def baseline(self): return read_baseline(self.root)
    def structured_summary(self,n=20): return self.manager.summary(n)
    def forget(self,query,limit=10): return self.manager.forget(query,limit)
    def correct(self,query,new_value,kind=None): return self.manager.correct(query,new_value,kind)
    def learn_explicit(self,text): return self.manager.learn_explicit(text)
    def recent(self,n=12):
        items=[]
        for k in ("facts","preferences","tasks"): items += [{"kind":k,**x} for x in self.data.get(k,[])]
        return sorted(items,key=lambda x:x.get("time",0))[-n:]
