"""Phase 13 durable lessons and workflow adaptation primitives."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
@dataclass
class Lesson:
    key:str; value:str; confidence:float=1.0; source:str='interaction'
class LearningStore:
    VERSION='v3.45.0'
    def __init__(self,path: str|Path): self.path=Path(path); self.lessons={}
    def learn(self,key,value,confidence=1.0,source='interaction'):
        if not key.strip() or not value.strip(): raise ValueError('key/value required')
        self.lessons[key]=Lesson(key,value,max(0,min(1,float(confidence))),source); self.save(); return self.lessons[key]
    def get(self,key): return self.lessons.get(key)
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True); self.path.write_text(json.dumps({k:v.__dict__ for k,v in self.lessons.items()},indent=2),encoding='utf-8')
    def load(self):
        if not self.path.exists(): return
        raw=json.loads(self.path.read_text(encoding='utf-8')); self.lessons={k:Lesson(**v) for k,v in raw.items()}
