from dataclasses import dataclass, field
from typing import Any
@dataclass
class SpecialistResult:
    specialist:str; answer:Any; confidence:float=0.0; evidence:list[str]=field(default_factory=list)
@dataclass
class CouncilDecision:
    answer:Any; confidence:float; contributors:list[str]; disagreements:list[str]=field(default_factory=list)
