"""Guarded self-improvement lab.

Only explicit, bounded file changes inside an allowed root are supported.
Every change is snapshotted, hashed, tested, and rolled back on failure.
No permission expansion or secret modification is performed here.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib, json, shutil, time, uuid

FORBIDDEN_NAMES={".env","credentials.json","secrets.json","id_rsa","authorized_keys"}

@dataclass
class ImprovementResult:
    ok: bool
    changed: bool
    tested: bool
    rolled_back: bool
    proposal_id: str
    reason: str
    before_sha256: str|None=None
    after_sha256: str|None=None

class ImprovementLab:
    def __init__(self, root, backup_root=None):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.backup_root=Path(backup_root or (self.root/"improvement_backups")).resolve()
        self.backup_root.mkdir(parents=True,exist_ok=True)

    def _safe(self,path):
        p=Path(path).resolve()
        if self.root not in p.parents and p != self.root: raise ValueError("path outside improvement root")
        if p.name.lower() in {x.lower() for x in FORBIDDEN_NAMES}: raise ValueError("protected file")
        return p

    @staticmethod
    def _sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

    def propose(self,path,old_text,new_text,reason):
        p=self._safe(path)
        return {"proposal_id":uuid.uuid4().hex[:12],"path":str(p),
                "reason":str(reason)[:1000],"old_sha256":self._sha(p),
                "old_text_present":old_text in p.read_text(encoding="utf-8") if p.exists() else False,
                "new_size":len(new_text)}

    def apply(self,path,old_text,new_text,test=None,reason=""):
        proposal=self.propose(path,old_text,new_text,reason)
        pid=proposal["proposal_id"]; p=Path(proposal["path"])
        if not p.exists(): return ImprovementResult(False,False,False,False,pid,"target_missing")
        original=p.read_text(encoding="utf-8")
        if old_text not in original: return ImprovementResult(False,False,False,False,pid,"expected_text_not_found")
        backup=self.backup_root/(pid+"_"+p.name)
        backup.write_text(original,encoding="utf-8")
        before=self._sha(p)
        candidate=original.replace(old_text,new_text,1)
        p.write_text(candidate,encoding="utf-8")
        tested=False
        try:
            if test is not None:
                result=test()
                tested=bool(result)
                if not tested: raise RuntimeError("test_failed")
            after=self._sha(p)
            return ImprovementResult(True,True,tested,False,pid,"improvement_applied",before,after)
        except Exception as exc:
            shutil.copy2(backup,p)
            return ImprovementResult(False,False,tested,True,pid,f"rolled_back:{type(exc).__name__}",before,self._sha(p))
