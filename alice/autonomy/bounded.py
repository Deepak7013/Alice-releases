import time
from dataclasses import dataclass, field
from typing import Callable, Any
@dataclass
class Budget:
    max_steps:int=10; max_seconds:float=60.0; used_steps:int=0
    def __post_init__(self):
        if self.max_steps<1 or self.max_seconds<=0: raise ValueError('finite positive budget required')
    def consume(self, started):
        if self.used_steps>=self.max_steps: raise RuntimeError('autonomy step budget exhausted')
        if time.monotonic()-started >= self.max_seconds: raise RuntimeError('autonomy time budget exhausted')
        self.used_steps+=1
class BoundedAutonomy:
    """Runs low-risk, pre-approved work under explicit step/time budgets; no permission expansion."""
    def __init__(self,budget=None): self.budget=budget or Budget()
    def run(self, actions:list[Callable[[],Any]]) -> list[Any]:
        started=time.monotonic(); results=[]
        for action in actions:
            self.budget.consume(started); results.append(action())
        return results
