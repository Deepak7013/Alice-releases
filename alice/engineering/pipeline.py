from dataclasses import dataclass
from typing import Callable, Optional
from .models import EngineeringGoal, BuildResult, BuildStatus
from .engine import EngineeringEngine

@dataclass
class EngineeringPipeline:
    engine: EngineeringEngine
    max_repair_iterations: int = 3

    def run(self, goal: EngineeringGoal, workspace: str,
            build_fn: Optional[Callable[[str], None]] = None,
            test_fn: Optional[Callable[[str], tuple]] = None) -> BuildResult:
        plan = self.engine.plan(goal)
        project = self.engine.scaffold(plan, workspace)
        iterations = 0
        if build_fn:
            build_fn(str(project))
        while iterations <= self.max_repair_iterations:
            iterations += 1
            if test_fn:
                passed, failed = test_fn(str(project))
            else:
                passed, failed = (0, 0)
            if failed == 0:
                return self.engine.verify_result(str(project), passed, failed, iterations)
            if iterations >= self.max_repair_iterations:
                break
            if build_fn:
                build_fn(str(project))
        return self.engine.verify_result(str(project), passed, failed, iterations)
