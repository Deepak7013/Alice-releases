from __future__ import annotations
from dataclasses import dataclass,field
from time import monotonic
from threading import RLock
@dataclass
class ResourceBudget:
    max_workers:int=4; max_parallel:int=4; max_runtime_seconds:int=1800; max_output_bytes:int=2_000_000
@dataclass
class ResourceLease:
    owner:str; kind:str; acquired:float; metadata:dict=field(default_factory=dict)
class ResourceManager:
    def __init__(self,budget=None): self.budget=budget or ResourceBudget(); self._leases={}; self._lock=RLock()
    def acquire(self,owner,kind,metadata=None):
        with self._lock:
            if len(self._leases)>=self.budget.max_parallel: return None
            key=f'{owner}:{kind}'
            if key in self._leases:return self._leases[key]
            lease=ResourceLease(owner,kind,monotonic(),metadata or {});self._leases[key]=lease;return lease
    def release(self,owner,kind):
        with self._lock:return self._leases.pop(f'{owner}:{kind}',None) is not None
    def snapshot(self):
        with self._lock:return {k:{'owner':v.owner,'kind':v.kind,'age':max(0,monotonic()-v.acquired),'metadata':dict(v.metadata)} for k,v in self._leases.items()}
    def can_parallelize(self,count=1): return len(self._leases)+int(count)<=self.budget.max_parallel
