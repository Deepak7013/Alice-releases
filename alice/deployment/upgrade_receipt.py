from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib

@dataclass(frozen=True)
class UpgradeReceipt:
    version: str
    candidate: str
    files: tuple[str, ...]
    evidence_digest: str
    ready: bool
    executed: bool = False
    def as_dict(self): return asdict(self)

def create_receipt(version, candidate, files, evidence):
    rows = [str(x) for x in files]
    payload = "\n".join([str(version), str(candidate), *rows, repr(evidence)])
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return UpgradeReceipt(str(version), str(candidate), tuple(rows), digest, bool(rows and evidence), False)
