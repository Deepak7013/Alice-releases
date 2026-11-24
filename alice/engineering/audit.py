import json,time,hashlib
from pathlib import Path
class EngineeringAudit:
 def __init__(self,root=None,limit=1000): self.path=Path(root or Path.cwd())/'alice_workspace'/'engineering_audit.json'; self.limit=int(limit); self.path.parent.mkdir(parents=True,exist_ok=True); self.items=self._load()
 def _load(self):
  try:return json.loads(self.path.read_text(encoding='utf-8'))
  except Exception:return []
 def record(self,event,details):
  safe=details if isinstance(details,dict) else {'value':str(details)}; row={'event':str(event),'details':safe,'created_at':time.time()}; row['event_id']=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()[:20]; self.items=(self.items+[row])[-self.limit:]; tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps(self.items,indent=2),encoding='utf-8'); tmp.replace(self.path); return row
 def list(self,event=None): return [x for x in self.items if event is None or x.get('event')==event]
