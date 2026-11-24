from __future__ import annotations
import json,uuid
from pathlib import Path
from datetime import datetime,timezone
class NotificationMirror:
    def __init__(self,root=None): self.path=Path(root or Path.cwd())/'alice_workspace'/'android'/'notifications.json'; self.path.parent.mkdir(parents=True,exist_ok=True); self.items=self._load()
    def _load(self):
        try:return json.loads(self.path.read_text())
        except Exception:return []
    def ingest(self,package,title,text,posted_at=None):
        x={'id':uuid.uuid4().hex[:12],'package':package,'title':title,'text':text,'posted_at':posted_at or datetime.now(timezone.utc).isoformat(),'read':False}; self.items.append(x); self.path.write_text(json.dumps(self.items,indent=2)); return dict(x)
    def list(self,package=None,unread_only=False): return [x for x in self.items if (package is None or x['package']==package) and (not unread_only or not x['read'])]
    def mark_read(self,nid):
        for x in self.items:
            if x['id']==nid: x['read']=True; self.path.write_text(json.dumps(self.items,indent=2)); return dict(x)
        raise KeyError(nid)
