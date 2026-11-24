from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict

class ProactiveAction(str, Enum):
    IGNORE = "ignore"
    INFORM = "inform"
    RECOMMEND = "recommend"
    RESEARCH = "research"
    ASK = "ask"
    PREPARE = "prepare"

@dataclass
class Opportunity:
    title: str
    reason: str
    evidence: List[str] = field(default_factory=list)
    urgency: float = 0.0
    confidence: float = 0.5
    consequence: float = 0.0

@dataclass
class ProactiveDecision:
    action: ProactiveAction
    opportunity: Opportunity
    explanation: str
    requires_confirmation: bool = False
