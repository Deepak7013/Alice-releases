from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json,time
from pathlib import Path

@dataclass(frozen=True)
class ProvenanceRecord:
    fingerprint:str; topic:str; source:str; confidence:float; created_at:float
    def as_dict(self): return asdict(self)

class LearningProvenance:
    """Append-only local provenance index for learned knowledge decisions."""
    def __init__(self, root=None):
        self.path=Path(root or Path.cwd())/'alice_workspace'/'learning_provenance.jsonl'; self.path.parent.mkdir(parents=True,exist_ok=True)
    def record(self,text,topic,source='user_chat',confidence=.95):
        raw=' '.join(str(text).split()); fp=hashlib.sha256(raw.lower().encode()).hexdigest()
        rec=ProvenanceRecord(fp,str(topic),str(source),max(0,min(1,float(confidence))),time.time())
        with self.path.open('a',encoding='utf-8') as f: f.write(json.dumps(asdict(rec),sort_keys=True)+'\n')
        return rec
    def seen(self,fingerprint):
        if not self.path.exists(): return False
        for line in self.path.read_text(encoding='utf-8').splitlines():
            try:
                if json.loads(line).get('fingerprint')==fingerprint: return True
            except Exception: pass
        return False
