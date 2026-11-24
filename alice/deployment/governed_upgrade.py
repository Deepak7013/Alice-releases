from __future__ import annotations
from dataclasses import dataclass,asdict
from alice.engineering.integrity_gate import IntegrityGate
from alice.deployment.upgrade_bundle import plan_upgrade
@dataclass(frozen=True)
class GovernedUpgradeResult:
 verified:bool; integrity_ok:bool; bundle_ready:bool; executed:bool=False
 def as_dict(self): return asdict(self)
class GovernedUpgradeController:
 def __init__(self,integrity_gate=None): self.integrity=integrity_gate or IntegrityGate()
 def evaluate(self,impact,baseline=None,current=None,protected_ok=True,version='',candidate='',files=None,approval=False):
  integrity=self.integrity.evaluate(impact,baseline,current,protected_ok); bundle=plan_upgrade(version,candidate,files or [],integrity.eligible,approval)
  return GovernedUpgradeResult(integrity.eligible,integrity.eligible,bundle.ready,False)
