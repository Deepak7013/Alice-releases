
"""Persistent, bounded global experience memory for reusable task workflows."""
from __future__ import annotations
import json, time, re, hashlib
from pathlib import Path
from dataclasses import dataclass, asdict, field

@dataclass
class ExperienceRecord:
    task: str
    workflow: str
    success: bool
    duration_ms: int = 0
    evidence: dict = field(default_factory=dict)
    tools: list = field(default_factory=list)
    context: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

class GlobalExperienceStore:
    """Stores reusable experience, never permissions or secrets."""
    def __init__(self, root=None, max_records=1000):
        base=Path(root or Path(__file__).resolve().parents[2])/"alice_workspace"
        self.path=base/"global_experience.json"
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.max_records=max(1,int(max_records))
        self.records=self._load()

    def _load(self):
        try:
            data=json.loads(self.path.read_text(encoding="utf-8"))
            return [ExperienceRecord(**x) for x in data if isinstance(x,dict)]
        except Exception:
            return []

    @staticmethod
    def _clean(v):
        sensitive=re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization|credential)")
        if isinstance(v,(bool,int,float)) or v is None: return v
        if isinstance(v,list): return [GlobalExperienceStore._clean(x) for x in v[:100]]
        if isinstance(v,dict):
            out={}
            for k,x in list(v.items())[:100]:
                sk=str(k)
                out[sk]="[REDACTED]" if sensitive.search(sk) else GlobalExperienceStore._clean(x)
            return out
        s=str(v)
        s=re.sub(r"(?i)(api[_-]?key|token|password|secret|authorization|credential)\s*[:=]\s*\S+","[REDACTED]",s)
        return s[:2000]

    def _save(self):
        tmp=self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(x) for x in self.records[-self.max_records:]],
                                  indent=2,ensure_ascii=False),encoding="utf-8")
        tmp.replace(self.path)

    def record(self, task, workflow, success, *, duration_ms=0, evidence=None, tools=None, context=None):
        rec=ExperienceRecord(self._clean(task),self._clean(workflow),bool(success),
            max(0,int(duration_ms)),self._clean(evidence or {}),self._clean(tools or []),
            self._clean(context or {}))
        self.records.append(rec); self.records=self.records[-self.max_records:]; self._save()
        return rec

    def recall(self, task, *, limit=10, success_only=True):
        target=self._tokens(task); scored=[]
        for r in self.records:
            if success_only and not r.success: continue
            toks=self._tokens(r.task)
            score=(len(target&toks)/len(target|toks)) if target and toks else 0.0
            if score>0:
                scored.append((score,r))
        scored.sort(key=lambda x:(x[0],x[1].created_at),reverse=True)
        return [{"similarity":round(s,3),"experience":asdict(r)} for s,r in scored[:max(0,int(limit))]]

    def stats(self):
        total=len(self.records); good=sum(r.success for r in self.records)
        return {"records":total,"successful":good,"failed":total-good}

    @staticmethod
    def _tokens(value):
        return {x for x in re.findall(r"[a-z0-9]+",str(value).lower()) if len(x)>1}
