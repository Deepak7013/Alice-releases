from __future__ import annotations
from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class UpgradeBundlePlan:
 version:str; candidate:str; files:list[str]; verified:bool; approved:bool; ready:bool
 def as_dict(self): return asdict(self)
def plan_upgrade(version,candidate,files,verified=False,approved=False):
 return UpgradeBundlePlan(str(version),str(candidate),[str(x) for x in files],bool(verified),bool(approved),bool(verified and approved and files))
