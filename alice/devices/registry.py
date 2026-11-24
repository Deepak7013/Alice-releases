from __future__ import annotations
import json, uuid
from pathlib import Path
from datetime import datetime, timezone

def now(): return datetime.now(timezone.utc).isoformat()
class DeviceRegistry:
    def __init__(self, root=None):
        self.root=Path(root or Path.cwd()); self.path=self.root/'alice_workspace'/'devices'/'registry.json'; self.path.parent.mkdir(parents=True,exist_ok=True); self.data=self._load()
    def _load(self):
        try:return json.loads(self.path.read_text())
        except Exception:return {}
    def _save(self): self.path.write_text(json.dumps(self.data,indent=2))
    def register(self,name,kind,capabilities=(),device_id=None):
        did=device_id or uuid.uuid4().hex[:12]
        self.data[did]={'id':did,'name':str(name),'kind':str(kind),'capabilities':sorted(set(capabilities)),'online':False,'last_seen':None,'paired':False}
        self._save(); return dict(self.data[did])
    def set_online(self,device_id,online=True):
        if device_id not in self.data: raise KeyError(device_id)
        self.data[device_id]['online']=bool(online); self.data[device_id]['last_seen']=now() if online else self.data[device_id]['last_seen']; self._save(); return dict(self.data[device_id])
    def pair(self,device_id):
        if device_id not in self.data: raise KeyError(device_id)
        self.data[device_id]['paired']=True; self._save(); return dict(self.data[device_id])
    def get(self,device_id): return dict(self.data[device_id]) if device_id in self.data else None
    def find_capability(self,capability,online_only=True): return [dict(v) for v in self.data.values() if capability in v['capabilities'] and (not online_only or v['online'])]
