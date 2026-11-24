import json,time,uuid
from pathlib import Path
from .models import Project,ProjectTask
class ProjectStore:
 def __init__(self,root=None): self.root=Path(root or Path(__file__).resolve().parents[2]); self.path=self.root/'alice_workspace'/'projects.json'; self.path.parent.mkdir(parents=True,exist_ok=True); self.data=self._load()
 def _load(self):
  try:return json.loads(self.path.read_text())
  except (FileNotFoundError,json.JSONDecodeError):return {'projects':{},'tasks':{}}
 def _save(self): t=self.path.with_suffix('.tmp'); t.write_text(json.dumps(self.data,indent=2)); t.replace(self.path)
 def add_project(self,name,description='',tags=None,project_id=None):
  if not name.strip(): raise ValueError('name is required')
  pid=project_id or uuid.uuid4().hex[:12]
  if pid in self.data['projects']: raise FileExistsError(pid)
  p=Project(pid,name.strip(),description,tags=tags or []); self.data['projects'][pid]=p.__dict__; self._save(); return p
 def add_task(self,project_id,title,priority='normal',due_at=None,dependencies=None,task_id=None):
  if project_id not in self.data['projects']: raise KeyError(project_id)
  if priority not in {'low','normal','high','urgent'}: raise ValueError('invalid priority')
  tid=task_id or uuid.uuid4().hex[:12]; t=ProjectTask(tid,title,'todo',priority,due_at,dependencies or [],project_id); self.data['tasks'][tid]=t.__dict__; self._save(); return t
 def tasks(self,project_id=None): return [ProjectTask(**x) for x in self.data['tasks'].values() if project_id is None or x['project_id']==project_id]
 def set_task_status(self,task_id,status):
  if status not in {'todo','in_progress','blocked','done','cancelled'}: raise ValueError('invalid status')
  if task_id not in self.data['tasks']: raise KeyError(task_id)
  self.data['tasks'][task_id]['status']=status; self._save(); return ProjectTask(**self.data['tasks'][task_id])
 def blocked_tasks(self,project_id):
  ts={x.task_id:x for x in self.tasks(project_id)}; return [x for x in ts.values() if x.status!='done' and any(ts.get(d) and ts[d].status!='done' for d in x.dependencies)]
