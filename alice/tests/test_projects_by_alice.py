import tempfile
from pathlib import Path

from alice.builder.engine import BuilderEngine


class DummyRouter:
    def ask(self, prompt):
        return "{}"


def test_builder_uses_projects_by_alice_root(tmp_path):
    engine = BuilderEngine(DummyRouter(), root=tmp_path)
    assert engine.projects == (tmp_path / "projects_by_alice").resolve()
    assert engine.projects.exists()


def test_generated_project_stays_outside_alice_core(tmp_path):
    engine = BuilderEngine(DummyRouter(), root=tmp_path)
    project = engine._safe_project("cyclehub")
    assert project == (tmp_path / "projects_by_alice" / "cyclehub").resolve()
    assert not (tmp_path / "alice" / "cyclehub").exists()
    assert not (tmp_path / "alice_workspace" / "projects" / "cyclehub").exists()
