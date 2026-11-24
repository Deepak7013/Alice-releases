from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class UpgradeContinuity:
 current:str; parent:str; receipt_bound:bool; health_passed:bool; continuation_allowed:bool; reason:str
 def as_dict(self): return asdict(self)
def evaluate(current,parent,*,receipt_bound,health_passed,unfinished=False,blocked=False):
 current=str(current).strip(); parent=str(parent).strip()
 if not current or not parent or current==parent: return UpgradeContinuity(current,parent,bool(receipt_bound),bool(health_passed),False,'distinct current and parent versions required')
 if not receipt_bound: return UpgradeContinuity(current,parent,False,bool(health_passed),False,'upgrade receipt is not bound')
 if not health_passed: return UpgradeContinuity(current,parent,True,False,False,'post-upgrade health gate failed')
 if blocked: return UpgradeContinuity(current,parent,True,True,False,'continuation is blocked')
 return UpgradeContinuity(current,parent,True,True,bool(unfinished),'unfinished work may continue' if unfinished else 'upgrade is complete')
