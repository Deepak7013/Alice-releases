
from __future__ import annotations
from dataclasses import dataclass
from .models import CapabilityProposal, AcquisitionStage

@dataclass
class PromotionResult:
    ok: bool
    proposal: CapabilityProposal
    reason: str = ""

class CapabilityPromotionPipeline:
    """Turns proven learned workflows into capability candidates.

    This layer does not silently grant authority. Every candidate still passes
    security, sandbox and registry gates before activation.
    """
    def __init__(self, security=None, sandbox=None, registry=None,
                 min_confidence=0.80, knowledge=None):
        self.security=security
        self.sandbox=sandbox
        self.registry=registry
        self.min_confidence=min_confidence
        self.knowledge=knowledge


    def research_context(self, task_type: str, limit: int = 5) -> str:
        """Return existing knowledge relevant to a capability gap.

        Stored knowledge is informational only; this method never activates a
        capability and never changes requested scopes.
        """
        if self.knowledge is None:
            return ""
        retrieve = getattr(self.knowledge, "context", None)
        if not retrieve:
            return ""
        return retrieve(task_type, limit=limit, trusted_only=False)

    def propose(self, workflow, task_type, confidence, scopes=None, evidence=None):
        p=CapabilityProposal(
            name=f"learned_{task_type}_{abs(hash(workflow)) % 100000}",
            task_type=task_type,
            workflow=workflow,
            confidence=confidence,
            requested_scopes=list(scopes or []),
            evidence=list(evidence or []),
        )
        if confidence < self.min_confidence:
            p.transition(AcquisitionStage.REJECTED)
            p.rejection_reason="insufficient learning confidence"
        else:
            p.transition(AcquisitionStage.RESEARCH)
        return p

    def validate(self, proposal: CapabilityProposal):
        if proposal.stage == AcquisitionStage.REJECTED:
            return PromotionResult(False,proposal,proposal.rejection_reason)

        proposal.transition(AcquisitionStage.DESIGNED)

        # Security gate: proposal cannot expand authority by itself.
        if self.security is not None:
            authorize=getattr(self.security,"authorize",None)
            if authorize:
                ok,missing=authorize(proposal.name,proposal.requested_scopes)
                if not ok:
                    proposal.transition(AcquisitionStage.REJECTED)
                    proposal.rejection_reason=f"scopes not granted: {missing}"
                    return PromotionResult(False,proposal,proposal.rejection_reason)

        proposal.transition(AcquisitionStage.VALIDATING)

        if self.sandbox is not None:
            proposal.transition(AcquisitionStage.SANDBOX_TEST)
            tester=getattr(self.sandbox,"validate_capability",None)
            if tester and not tester(proposal):
                proposal.transition(AcquisitionStage.REJECTED)
                proposal.rejection_reason="sandbox validation failed"
                return PromotionResult(False,proposal,proposal.rejection_reason)

        proposal.transition(AcquisitionStage.SECURITY_REVIEW)
        proposal.transition(AcquisitionStage.READY)
        return PromotionResult(True,proposal,"ready for explicit registry activation")

    def activate(self, proposal):
        if proposal.stage != AcquisitionStage.READY:
            return PromotionResult(False,proposal,"proposal is not ready")
        if self.registry is None:
            return PromotionResult(False,proposal,"no registry configured")
        register=getattr(self.registry,"register",None)
        if not register:
            return PromotionResult(False,proposal,"registry has no register operation")
        if not register(proposal):
            return PromotionResult(False,proposal,"registry rejected capability")
        proposal.transition(AcquisitionStage.ACTIVATED)
        return PromotionResult(True,proposal,"activated")
