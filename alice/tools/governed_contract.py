"""Governed tool contracts for the Action/Devour boundary.

Metadata/preflight only: this contract never grants permission or executes a tool.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict

@dataclass(frozen=True)
class ToolContract:
    name: str
    risk: str = "read"
    permissions: tuple[str, ...] = field(default_factory=tuple)
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    verified: bool = False
    source: str = "alice"

class ToolContractGate:
    ALLOWED_RISKS = {"read", "write", "execute", "external"}
    def validate(self, contract: ToolContract) -> dict:
        if not contract.name.strip(): return {"allowed":False,"reason":"missing_name"}
        if contract.risk not in self.ALLOWED_RISKS: return {"allowed":False,"reason":"invalid_risk"}
        if contract.risk != "read" and not contract.permissions: return {"allowed":False,"reason":"permissions_required"}
        if not contract.verified: return {"allowed":False,"reason":"tool_not_verified"}
        return {"allowed":True,"reason":"contract_valid","contract":asdict(contract)}
