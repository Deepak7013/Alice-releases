"""Persistent, inert ledger for governed engineering runs."""
from __future__ import annotations
import json, time, hashlib
from pathlib import Path

class EngineeringRunLedger:
    def __init__(self, root=None):
        self.path=Path(root or Path.cwd())/"alice_workspace"/"engineering_runs.json"
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.items=self._load()
    def _load(self):
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: return []
    def _save(self):
        tmp=self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(self.items,indent=2),encoding="utf-8"); tmp.replace(self.path)
    def record(self, proposal_id, plan_name, impact, status="preflighted"):
        payload={"proposal_id":str(proposal_id),"plan_name":str(plan_name),"impact":impact if isinstance(impact,dict) else {},"status":str(status)}
        rid=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:20]
        row={"run_id":rid,**payload,"created_at":time.time()}
        if not any(x.get("run_id")==rid for x in self.items):
            self.items.append(row); self.items=self.items[-500:]; self._save()
        return next(x for x in self.items if x.get("run_id")==rid)
    def list(self, proposal_id=None, status=None):
        return [x for x in self.items if (proposal_id is None or x.get("proposal_id")==proposal_id) and (status is None or x.get("status")==status)]
