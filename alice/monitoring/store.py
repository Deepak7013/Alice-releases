import json,time,uuid
from pathlib import Path
from .models import Watch,Notification
class MonitoringStore:
 def __init__(self,root=None):
  self.root=Path(root or Path(__file__).resolve().parents[2]); self.path=self.root/'alice_workspace'/'monitoring.json'; self.path.parent.mkdir(parents=True,exist_ok=True); self.data=self._load()
 def _load(self):
  try:return json.loads(self.path.read_text())
  except (FileNotFoundError,json.JSONDecodeError):return {'watches':{},'notifications':{}}
 def _save(self):
  t=self.path.with_suffix('.tmp'); t.write_text(json.dumps(self.data,indent=2)); t.replace(self.path)
 def add_watch(self,kind,title,due_at=None,interval_seconds=None,payload=None,watch_id=None):
  if kind not in {'deadline','calendar','condition','recurring'}: raise ValueError('invalid watch kind')
  if not str(title).strip(): raise ValueError('title is required')
  if due_at is not None and due_at<0: raise ValueError('invalid due_at')
  if interval_seconds is not None and interval_seconds<60: raise ValueError('interval_seconds must be >= 60')
  wid=watch_id or uuid.uuid4().hex[:12]
  if wid in self.data['watches']: raise FileExistsError(wid)
  w=Watch(wid,kind,title,due_at,interval_seconds,True,payload or {}); self.data['watches'][wid]=w.__dict__; self._save(); return w
 def watches(self): return [Watch(**x) for x in self.data['watches'].values()]
 def notify(self,title,body,severity='info',source_id=None):
  n=Notification(uuid.uuid4().hex[:12],title,body,severity,source_id=source_id); self.data['notifications'][n.notification_id]=n.__dict__; self._save(); return n
 def notifications(self,unread_only=False):
  xs=[Notification(**x) for x in self.data['notifications'].values() if not unread_only or not x['read']]; return sorted(xs,key=lambda x:x.created_at)
 def mark_read(self,nid):
  if nid not in self.data['notifications']: raise KeyError(nid)
  self.data['notifications'][nid]['read']=True; self._save()
