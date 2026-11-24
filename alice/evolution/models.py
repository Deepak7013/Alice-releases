from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict

class EvolutionStatus(str, Enum):
    PROPOSED = "proposed"
    BACKED_UP = "backed_up"
    APPLYING = "applying"
    TESTING = "testing"
    SECURITY_REVIEW = "security_review"
    ACCEPTED = "accepted"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"

@dataclass
class EvolutionProposal:
    title: str
    reason: str
    files: List[str] = field(default_factory=list)
    expected_benefit: str = ""
    status: EvolutionStatus = EvolutionStatus.PROPOSED
    evidence: Dict[str, str] = field(default_factory=dict)
