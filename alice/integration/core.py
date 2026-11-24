from __future__ import annotations
from dataclasses import dataclass
from ..resources import ResourceManager
from ..deployment import DeploymentManager
@dataclass
class AliceSystemStatus:
    ready:bool; resources:dict; deployment:dict; audit_ok:bool
class AliceIntegration:
    def __init__(self,resource_manager=None,deployment_manager=None,audit_chain=None):
        self.resources=resource_manager or ResourceManager(); self.deployment=deployment_manager or DeploymentManager(); self.audit=audit_chain
    def status(self):
        audit_ok=True if self.audit is None else self.audit.verify()
        dep=self.deployment.preflight(); return AliceSystemStatus(bool(dep['ok'] and audit_ok),self.resources.snapshot(),dep,audit_ok)
    def preflight(self): return self.status().ready
