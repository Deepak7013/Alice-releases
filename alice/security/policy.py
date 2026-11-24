from __future__ import annotations
import json, os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

class TrustLevel(str, Enum):
    UNTRUSTED='untrusted'; REVIEWED='reviewed'; VERIFIED='verified'; BUILTIN='builtin'

@dataclass
class SecurityPolicy:
    allowed_scopes: set[str] = field(default_factory=set)
    trusted_capabilities: dict[str, TrustLevel] = field(default_factory=dict)
    def grant(self, capability: str, scopes: Iterable[str], trust: TrustLevel):
        self.allowed_scopes.update(scopes); self.trusted_capabilities[capability]=trust
    def authorize(self, capability: str, requested: Iterable[str]):
        missing=[s for s in requested if s not in self.allowed_scopes]
        return (not missing, missing)
    def trust_for(self, capability): return self.trusted_capabilities.get(capability, TrustLevel.UNTRUSTED)

class SecretStore:
    def __init__(self, path):
        self.path=Path(path); self.path.parent.mkdir(parents=True, exist_ok=True); self._data={}
        if self.path.exists():
            try: self._data=json.loads(self.path.read_text())
            except Exception: self._data={}
    def set(self,name,value): self._data[name]=value; self._persist()
    def has(self,name): return name in self._data
    def get(self,name): return self._data.get(name)
    def names(self): return sorted(self._data)
    def export_env(self,names): return {n:self._data[n] for n in names if n in self._data}
    def _persist(self):
        self.path.write_text(json.dumps(self._data))
        try: os.chmod(self.path,0o600)
        except OSError: pass
