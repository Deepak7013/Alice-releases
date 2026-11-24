import json,uuid
from pathlib import Path
from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class Edge: source:str; relation:str; target:str
class KnowledgeGraph:
 def __init__(self,root=None):
  root=Path(root or Path(__file__).resolve().parents[2]); self.path=root/'alice_workspace'/'knowledge_graph.json'; self.path.parent.mkdir(parents=True,exist_ok=True); self.data=self._load()
 def _load(self):
  try:return json.loads(self.path.read_text())
  except (FileNotFoundError,json.JSONDecodeError):return {'nodes':{},'edges':[]}
 def _save(self): t=self.path.with_suffix('.tmp'); t.write_text(json.dumps(self.data,indent=2)); t.replace(self.path)
 def node(self,label,node_id=None,kind='entity',metadata=None):
  nid=node_id or uuid.uuid4().hex[:12]; self.data['nodes'][nid]={'label':label,'kind':kind,'metadata':metadata or {}}; self._save(); return nid
 def link(self,source,relation,target):
  if source not in self.data['nodes'] or target not in self.data['nodes']: raise KeyError('unknown node')
  edge={'source':source,'relation':relation,'target':target}
  if edge not in self.data['edges']: self.data['edges'].append(edge); self._save()
  return Edge(**edge)
 def neighbors(self,node_id,relation=None):
  out=[]
  for e in self.data['edges']:
   if e['source']==node_id and (relation is None or e['relation']==relation): out.append(self.data['nodes'][e['target']]|{'id':e['target']})
  return out
 def related(self,a,b): return any(e['source']==a and e['target']==b for e in self.data['edges'])
