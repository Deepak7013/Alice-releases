"""Machine-readable self-model snapshot built from the capability graph."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import time

@dataclass
class SelfModelSnapshot:
    generated_at: float
    available: list[str]
    degraded: list[str]
    unavailable: list[str]
    unverified: list[str]
    configured_unverified: list[str]
    verified_count: int
    known_count: int

    @classmethod
    def build(cls, capability_manager):
        items = capability_manager.inventory()
        available=[]; degraded=[]; unavailable=[]; unverified=[]; configured_unverified=[]
        for c in items:
            name=c["name"]; status=c.get("status")
            if status == "available" and c.get("verified") and c.get("configured"): available.append(name)
            elif status == "degraded": degraded.append(name)
            elif status == "unavailable": unavailable.append(name)
            else: unverified.append(name)
            if status == "unverified" and c.get("configured"): configured_unverified.append(name)
        return cls(time.time(), sorted(available), sorted(degraded), sorted(unavailable), sorted(unverified), sorted(configured_unverified), sum(1 for c in items if c.get("verified")), len(items))

    def capability_gap(self, name):
        n=str(name).strip().lower().replace(" ", "_")
        if n in self.available: return {"name":n,"gap":False,"reason":"available"}
        if n in self.degraded: return {"name":n,"gap":True,"reason":"degraded"}
        if n in self.unverified: return {"name":n,"gap":True,"reason":"unverified"}
        return {"name":n,"gap":True,"reason":"unknown"}

    def to_dict(self): return asdict(self)
