from dataclasses import dataclass, field
from typing import Any
@dataclass
class ComponentCheck:
    name:str; ok:bool; detail:str=''; critical:bool=False; metadata:dict[str,Any]=field(default_factory=dict)
@dataclass
class HealthReport:
    checks:list[ComponentCheck]
    @property
    def ok(self): return all(c.ok for c in self.checks if c.critical) and bool(self.checks)
    @property
    def degraded(self): return any(not c.ok for c in self.checks)
    def as_dict(self): return {'ok':self.ok,'degraded':self.degraded,'checks':[c.__dict__ for c in self.checks]}
