from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
@dataclass(frozen=True)
class ExperienceHint:
    reusable: bool; examples: int; tools: tuple[str,...]; reason: str
@dataclass(frozen=True)
class ExperiencePreflight:
    request: str; hint: ExperienceHint; advisory_only: bool=True
class ExperienceAwarePreflight:
    def __init__(self, experience): self.experience=experience
    def inspect(self, request: str) -> ExperiencePreflight:
        rec=self.experience.recommend(request)
        return ExperiencePreflight(str(request), ExperienceHint(bool(rec.get('reusable')),int(rec.get('examples',0)),tuple(rec.get('tools',[])),str(rec.get('reason',''))))
    @staticmethod
    def to_dict(result: ExperiencePreflight)->dict[str,Any]: return asdict(result)
