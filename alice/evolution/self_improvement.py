from dataclasses import dataclass,asdict
from alice.engineering.cycle import GovernedEngineeringCycle
from alice.engineering.promotion import PromotionGate
@dataclass(frozen=True)
class ImprovementRun:
 proposal_id:str; verified:bool; promotion_eligible:bool; promoted:bool=False
 def as_dict(self): return asdict(self)
class SelfImprovementOrchestrator:
 def __init__(self,cycle=None,gate=None): self.cycle=cycle or GovernedEngineeringCycle(); self.gate=gate or PromotionGate()
 def run(self,proposal_id,goal,source_root,workspace,changes,test_fn=None,approval=False,protected_ok=True):
  c=self.cycle.run(proposal_id,goal,source_root,workspace,changes,test_fn); d=self.gate.evaluate({'verified':c.verified},approval=approval,protected_ok=protected_ok)
  return ImprovementRun(str(proposal_id),c.verified,d.eligible,False)
