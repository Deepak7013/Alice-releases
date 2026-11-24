import tempfile
from pathlib import Path

import pytest

from alice.workspace import PersonalWorkspace


def test_project_lifecycle_and_documents():
    with tempfile.TemporaryDirectory() as d:
        ws = PersonalWorkspace(d)
        project = ws.create_project("Alice Notes", project_id="notes", tags=["personal", "ai"])
        assert project.project_id == "notes"
        assert ws.get_project("notes").name == "Alice Notes"

        ws.write_document("notes", "plans/today.md", "Build Alice\nTest Alice\nShip only when verified")
        ws.write_document("notes", "ideas.txt", "Personal workspace should stay local")
        assert ws.read_document("notes", "plans/today.md").startswith("Build Alice")
        docs = ws.list_documents("notes")
        assert [x.path for x in docs] == ["ideas.txt", "plans/today.md"]

        hits = ws.search("verified")
        assert len(hits) == 1 and hits[0].line == 3

        updated = ws.update_project("notes", status="completed", tags=["done"])
        assert updated.status == "completed" and updated.tags == ["done"]
        assert ws.delete_document("notes", "ideas.txt") is True
        assert ws.delete_document("notes", "ideas.txt") is False


def test_workspace_blocks_path_escape():
    with tempfile.TemporaryDirectory() as d:
        ws = PersonalWorkspace(d)
        ws.create_project("Safe", project_id="safe")
        with pytest.raises(PermissionError):
            ws.write_document("safe", "../../escape.txt", "blocked")
        with pytest.raises(PermissionError):
            ws.read_document("safe", "../safe/../../escape.txt")


def test_project_ids_and_status_are_validated():
    with tempfile.TemporaryDirectory() as d:
        ws = PersonalWorkspace(d)
        with pytest.raises(ValueError):
            ws.create_project("Bad", project_id="../bad")
        ws.create_project("Good", project_id="good")
        with pytest.raises(ValueError):
            ws.update_project("good", status="unknown")


def test_persistence_and_snapshot():
    with tempfile.TemporaryDirectory() as d:
        ws = PersonalWorkspace(d)
        ws.create_project("Persist", project_id="persist")
        ws.write_document("persist", "note.md", "hello")
        snap = ws.snapshot("before-change")
        assert (snap / "projects" / "persist" / "note.md").read_text() == "hello"

        ws2 = PersonalWorkspace(d)
        assert ws2.get_project("persist") is not None
        assert ws2.read_document("persist", "note.md") == "hello"
        with pytest.raises(FileExistsError):
            ws2.snapshot("before-change")
