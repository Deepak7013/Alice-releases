from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional

class BuildStatus(str, Enum):
    PLANNED = "planned"
    RESEARCHING = "researching"
    BUILDING = "building"
    TESTING = "testing"
    REPAIRING = "repairing"
    VERIFIED = "verified"
    FAILED = "failed"

@dataclass
class EngineeringGoal:
    name: str
    description: str
    constraints: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)

@dataclass
class ProjectPlan:
    goal: EngineeringGoal
    requirements: List[str]
    components: List[str]
    test_plan: List[str]
    status: BuildStatus = BuildStatus.PLANNED

@dataclass
class BuildResult:
    status: BuildStatus
    project_path: str
    tests_passed: int = 0
    tests_failed: int = 0
    iterations: int = 0
    evidence: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
