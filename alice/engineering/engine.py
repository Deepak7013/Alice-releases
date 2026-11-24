from pathlib import Path
from .models import EngineeringGoal, ProjectPlan, BuildResult, BuildStatus

class EngineeringEngine:
    """Coordinates software construction without granting itself new authority."""

    def plan(self, goal: EngineeringGoal) -> ProjectPlan:
        requirements = list(goal.acceptance_criteria) or [goal.description]
        components = ["implementation", "tests", "documentation"]
        tests = ["syntax compilation", "unit tests", "acceptance criteria"]
        return ProjectPlan(goal, requirements, components, tests)

    def scaffold(self, plan: ProjectPlan, root: str) -> Path:
        path = Path(root)
        path.mkdir(parents=True, exist_ok=True)
        (path / "README.md").write_text(
            f"# {plan.goal.name}\n\n{plan.goal.description}\n", encoding="utf-8"
        )
        (path / "tests").mkdir(exist_ok=True)
        return path

    def verify_result(self, project_path: str, tests_passed: int, tests_failed: int,
                      iterations: int = 1) -> BuildResult:
        status = BuildStatus.VERIFIED if tests_failed == 0 else BuildStatus.FAILED
        return BuildResult(status, str(project_path), tests_passed, tests_failed, iterations)
