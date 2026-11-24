from pathlib import Path
import tempfile
from alice.engineering import EngineeringEngine, EngineeringGoal
from alice.engineering.pipeline import EngineeringPipeline
from alice.evolution import EvolutionManager
from alice.evolution.models import EvolutionStatus

def test_engineering_plan_and_verify():
    engine = EngineeringEngine()
    goal = EngineeringGoal("Demo AI", "Build a small AI", acceptance_criteria=["imports cleanly"])
    plan = engine.plan(goal)
    assert plan.requirements == ["imports cleanly"]
    with tempfile.TemporaryDirectory() as d:
        result = EngineeringPipeline(engine).run(goal, d)
        assert result.status.value == "verified"

def test_engineering_repair_bound():
    engine = EngineeringEngine()
    goal = EngineeringGoal("Failing", "demo")
    calls = {"n": 0}
    def tests(_):
        calls["n"] += 1
        return (0, 1)
    with tempfile.TemporaryDirectory() as d:
        result = EngineeringPipeline(engine, max_repair_iterations=3).run(goal, d, test_fn=tests)
        assert result.status.value == "failed"
        assert result.iterations == 3

def test_evolution_backup_and_rollback():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "src"
        backup = Path(d) / "backup"
        root.mkdir()
        target = root / "feature.py"
        target.write_text("old")
        m = EvolutionManager()
        p = m.propose("upgrade", "better", ["feature.py"])
        assert m.backup(str(root), str(backup), p)
        assert m.authorize(p)
        target.write_text("new")
        m.rollback(str(root), str(backup), p)
        assert target.read_text() == "old"
        assert p.status == EvolutionStatus.ROLLED_BACK

def test_evolution_rejects_forbidden_scope():
    m = EvolutionManager()
    p = m.propose("bad", "bad", ["feature.py"])
    assert not m.authorize(p, ["security_bypass"])
    assert p.status == EvolutionStatus.REJECTED

def test_evolution_rejects_protected_path():
    m = EvolutionManager()
    p = m.propose("bad", "bad", ["security/secrets.py"])
    assert not m.backup("/tmp", "/tmp/b", p)
    assert p.status == EvolutionStatus.REJECTED
