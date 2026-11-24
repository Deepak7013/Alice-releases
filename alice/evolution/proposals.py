from __future__ import annotations
import hashlib,json,time
from pathlib import Path
from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class ImprovementProposal:
 proposal_id:str;area:str;problem:str;evidence:str;expected_benefit:str;status:str;created_at:float
class ImprovementProposalLedger:
 def __init__(self,root=None):self.path=Path(root or Path.cwd())/'alice_workspace'/'improvement_proposals.json';self.path.parent.mkdir(parents=True,exist_ok=True);self.items=self._load()
 def _load(self):
  try:return json.loads(self.path.read_text(encoding='utf-8'))
  except Exception:return []
 def _save(self):
  tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.items,indent=2),encoding='utf-8');tmp.replace(self.path)
 def propose(self,area,problem,evidence,expected_benefit):
  evidence_text = json.dumps(evidence, sort_keys=True, ensure_ascii=False) if isinstance(evidence, (dict, list)) else str(evidence)
  pid=hashlib.sha256('|'.join(map(str,(area,problem,evidence_text,expected_benefit))).encode()).hexdigest()[:20]
  old=next((x for x in self.items if x.get('proposal_id')==pid),None)
  if old:return ImprovementProposal(**old)
  p=ImprovementProposal(pid,str(area)[:120],str(problem)[:800],evidence_text[:1000],str(expected_benefit)[:500],'proposed',time.time());self.items.append(asdict(p));self.items=self.items[-500:];self._save();return p
 def list(self,status=None):return [x for x in self.items if status is None or x.get('status')==status]
 def approve_for_engineering(self,proposal_id):
  for x in self.items:
   if x.get('proposal_id')==proposal_id and x.get('status')=='proposed':x['status']='engineering_review';self._save();return True
  return False
