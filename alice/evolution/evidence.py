from __future__ import annotations
import hashlib,json
class EvidenceBinder:
 def bind(self,proposal_id,evidence):
  safe=evidence if isinstance(evidence,dict) else {'value':str(evidence)}
  digest=hashlib.sha256(json.dumps(safe,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  return {'proposal_id':str(proposal_id),'evidence':safe,'evidence_hash':digest}
 def matches(self,bound,evidence): return self.bind(bound['proposal_id'],evidence)['evidence_hash']==bound.get('evidence_hash')
