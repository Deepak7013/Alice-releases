from __future__ import annotations
import json
from pathlib import Path
class DeviceConsent:
    def __init__(self,root=None): self.path=Path(root or Path.cwd())/'alice_workspace'/'security'/'device_consent.json'; self.path.parent.mkdir(parents=True,exist_ok=True); self.data=self._load()
    def _load(self):
        try:return json.loads(self.path.read_text())
        except Exception:return {}
    def grant(self,device_id,scopes): self.data[device_id]=sorted(set(scopes)); self.path.write_text(json.dumps(self.data,indent=2)); return self.data[device_id]
    def revoke(self,device_id,scope=None):
        if scope is None:self.data.pop(device_id,None)
        else:self.data[device_id]=[s for s in self.data.get(device_id,[]) if s!=scope]
        self.path.write_text(json.dumps(self.data,indent=2))
    def allowed(self,device_id,scope): return scope in self.data.get(device_id,[])
