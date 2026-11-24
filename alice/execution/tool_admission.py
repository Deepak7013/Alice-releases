"""Final pre-execution admission gate for governed tools.

The gate is intentionally side-effect free. It re-checks the selected tool,
requested capability and governed contract immediately before execution. It
never grants permission, changes authority, or executes the tool.
"""
from __future__ import annotations

from dataclasses import dataclass

from alice.tools.governed_contract import ToolContract, ToolContractGate


@dataclass(frozen=True)
class AdmissionDecision:
    admitted: bool
    reason: str
    tool: str | None = None


class ToolAdmissionGate:
    """Revalidate a resolved tool at the final execution boundary."""

    def __init__(self, contract_gate: ToolContractGate | None = None):
        self._contracts = contract_gate or ToolContractGate()

    def admit(self, *, capability: dict, tool: dict, contract: ToolContract) -> AdmissionDecision:
        if not capability or not capability.get("name"):
            return AdmissionDecision(False, "missing_capability")
        if not tool or not tool.get("name"):
            return AdmissionDecision(False, "missing_tool")
        if str(tool.get("name")) != contract.name:
            return AdmissionDecision(False, "tool_contract_name_mismatch")

        wanted = str(capability["name"]).strip().lower()
        capabilities = {str(x).strip().lower() for x in tool.get("capabilities", ())}
        if wanted not in capabilities:
            return AdmissionDecision(False, "capability_tool_mismatch")

        result = self._contracts.validate(contract)
        if not result.get("allowed"):
            return AdmissionDecision(False, str(result.get("reason", "contract_rejected")))

        if not tool.get("verified", False):
            return AdmissionDecision(False, "tool_not_verified")
        if not capability.get("verified", False):
            return AdmissionDecision(False, "capability_not_verified")

        return AdmissionDecision(True, "execution_admitted", contract.name)
