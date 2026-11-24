"""Bounded candidate repair controller."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RepairReport:
    iterations: int
    verified: bool
    stopped_reason: str

class RepairController:
    def __init__(self,max_iterations=3): self.max_iterations=max(0,int(max_iterations))
    def run(self, validate, repair):
        last=None
        for i in range(self.max_iterations+1):
            last=validate()
            if getattr(last,'verified',False): return RepairReport(i+1,True,'verified')
            if i>=self.max_iterations: return RepairReport(i+1,False,'repair_limit_reached')
            repaired=repair(i+1,last)
            if repaired is False: return RepairReport(i+1,False,'repair_refused')
        return RepairReport(self.max_iterations+1,False,'repair_limit_reached')
