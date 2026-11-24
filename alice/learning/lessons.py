from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json, time

@dataclass
class Lesson:
    key:str; value:str; confidence:float=1.0; source:str='interaction'; verified:bool=False; updated_at:float=0.0

class LearningStore:
    VERSION='v3.48.0'
    def __init__(self,path: str|Path):
        self.path=Path(path); self.lessons={}; self.load()
    def learn(self,key,value,confidence=1.0,source='interaction',verified=False):
        if not str(key).strip() or not str(value).strip(): raise ValueError('key/value required')
        self.lessons[str(key)]=Lesson(str(key),str(value),max(0,min(1,float(confidence))),str(source),bool(verified),time.time()); self.save(); return self.lessons[str(key)]
    def get(self,key,verified_only=False):
        lesson=self.lessons.get(key)
        if verified_only and (lesson is None or not lesson.verified): return None
        return lesson
    def verify(self,key,evidence='verified interaction'):
        lesson=self.lessons.get(key)
        if lesson is None: return None
        lesson.verified=True; lesson.source=f'{lesson.source}; {evidence}'; lesson.updated_at=time.time(); self.save(); return lesson
    def search(self,text,verified_only=False):
        q=str(text).lower(); return [x for x in self.lessons.values() if (not verified_only or x.verified) and (q in x.key.lower() or q in x.value.lower())]
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True); tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps({k:asdict(v) for k,v in self.lessons.items()},indent=2,ensure_ascii=False),encoding='utf-8'); tmp.replace(self.path)
    def load(self):
        if not self.path.exists(): return
        try:
            raw=json.loads(self.path.read_text(encoding='utf-8')); self.lessons={k:Lesson(**v) for k,v in raw.items()}
        except (OSError,ValueError,TypeError): self.lessons={}
