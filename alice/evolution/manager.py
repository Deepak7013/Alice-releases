from pathlib import Path
import shutil
from .models import EvolutionProposal, EvolutionStatus
from .policy import EvolutionPolicy

class EvolutionManager:
    def __init__(self, policy=None):
        self.policy = policy or EvolutionPolicy()

    def propose(self, title, reason, files, expected_benefit=""):
        return EvolutionProposal(title, reason, list(files), expected_benefit)

    def backup(self, source_root: str, backup_root: str, proposal: EvolutionProposal):
        ok, msg = self.policy.validate_paths(source_root, proposal.files)
        if not ok:
            proposal.status = EvolutionStatus.REJECTED
            proposal.evidence["policy"] = msg
            return False
        src = Path(source_root).resolve()
        dst = Path(backup_root).resolve()
        dst.mkdir(parents=True, exist_ok=True)
        for rel in proposal.files:
            s = src / rel
            if s.exists():
                d = dst / rel
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, d)
        proposal.status = EvolutionStatus.BACKED_UP
        return True

    def rollback(self, source_root: str, backup_root: str, proposal: EvolutionProposal):
        src, backup = Path(source_root), Path(backup_root)
        for rel in proposal.files:
            b = backup / rel
            if b.exists():
                target = src / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(b, target)
        proposal.status = EvolutionStatus.ROLLED_BACK

    def authorize(self, proposal: EvolutionProposal, permissions=None):
        ok, msg = self.policy.validate_scope(permissions or [])
        if not ok:
            proposal.status = EvolutionStatus.REJECTED
            proposal.evidence["policy"] = msg
            return False
        if not proposal.files:
            proposal.status = EvolutionStatus.REJECTED
            proposal.evidence["policy"] = "no source files selected"
            return False
        proposal.status = EvolutionStatus.APPLYING
        return True

    def accept(self, proposal, tests_passed, tests_failed, security_ok=True):
        proposal.evidence["tests_passed"] = str(tests_passed)
        proposal.evidence["tests_failed"] = str(tests_failed)
        proposal.evidence["security_ok"] = str(security_ok)
        if tests_failed == 0 and security_ok:
            proposal.status = EvolutionStatus.ACCEPTED
            return True
        proposal.status = EvolutionStatus.ROLLED_BACK
        return False
