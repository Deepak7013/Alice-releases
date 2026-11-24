from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class PromotionTransaction:
 candidate:str; target:str; files:list[str]; approved:bool; executable:bool
 def as_dict(self): return asdict(self)
PROTECTED={"alice_workspace",".env",".git",".venv"}
def plan_promotion(candidate,target,files,approved=False):
 safe=all(not any(x in PROTECTED for x in str(p).replace('\\','/').split('/')) for p in files)
 return PromotionTransaction(str(candidate),str(target),[str(x) for x in files],bool(approved),bool(approved and safe))
