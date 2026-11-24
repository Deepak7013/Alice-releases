"""Safe, persistent personal workspace management for Alice.

The workspace is deliberately file-system local and bounded to its configured root.
It manages project metadata and text documents without granting arbitrary system access.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Iterable, List, Optional

from .models import WorkspaceDocument, WorkspaceProject, WorkspaceSearchResult


_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


class PersonalWorkspace:
    """Manage Alice's personal projects, documents, and workspace snapshots."""

    def __init__(self, root=None):
        base = Path(root) if root is not None else Path(__file__).resolve().parents[2] / "alice_workspace" / "personal"
        self.root = base.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.projects_dir = self.root / "projects"
        self.projects_dir.mkdir(exist_ok=True)
        self.index_path = self.root / "projects.json"
        self._index = self._load_index()

    def _load_index(self):
        if not self.index_path.exists():
            return {}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_index(self):
        self._atomic_write(self.index_path, json.dumps(self._index, indent=2, ensure_ascii=False))

    @staticmethod
    def _atomic_write(path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".alice-", dir=str(path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass

    @staticmethod
    def _validate_id(value: str):
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise ValueError("Project id must contain only letters, numbers, '.', '_' or '-'.")

    def _project_root(self, project_id: str) -> Path:
        self._validate_id(project_id)
        p = (self.projects_dir / project_id).resolve()
        if self.projects_dir.resolve() not in p.parents:
            raise PermissionError("Project path escapes workspace")
        return p

    def _safe_project_path(self, project_id: str, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("Document path is required")
        root = self._project_root(project_id)
        candidate = (root / relative_path).resolve()
        if root not in candidate.parents and candidate != root:
            raise PermissionError("Document path escapes project workspace")
        return candidate

    def create_project(self, name: str, project_id: Optional[str] = None,
                       description: str = "", tags: Optional[Iterable[str]] = None) -> WorkspaceProject:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Project name is required")
        project_id = project_id or uuid.uuid4().hex[:12]
        self._validate_id(project_id)
        if project_id in self._index:
            raise FileExistsError(project_id)
        now = time.time()
        project = WorkspaceProject(project_id, name.strip(), description.strip(), "active",
                                   sorted({str(t).strip() for t in (tags or []) if str(t).strip()}), now, now)
        self._project_root(project_id).mkdir(parents=True, exist_ok=False)
        self._index[project_id] = project.__dict__.copy()
        self._save_index()
        return project

    def get_project(self, project_id: str) -> Optional[WorkspaceProject]:
        data = self._index.get(project_id)
        return WorkspaceProject(**data) if data else None

    def list_projects(self, status: Optional[str] = None) -> List[WorkspaceProject]:
        projects = [WorkspaceProject(**v) for v in self._index.values()]
        if status is not None:
            projects = [p for p in projects if p.status == status]
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def update_project(self, project_id: str, *, name: Optional[str] = None,
                       description: Optional[str] = None, status: Optional[str] = None,
                       tags: Optional[Iterable[str]] = None) -> WorkspaceProject:
        project = self.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        if name is not None:
            if not str(name).strip():
                raise ValueError("Project name cannot be empty")
            project.name = str(name).strip()
        if description is not None:
            project.description = str(description).strip()
        if status is not None:
            if status not in {"active", "paused", "completed", "archived"}:
                raise ValueError("Invalid project status")
            project.status = status
        if tags is not None:
            project.tags = sorted({str(t).strip() for t in tags if str(t).strip()})
        project.updated_at = time.time()
        self._index[project_id] = project.__dict__.copy()
        self._save_index()
        return project

    def write_document(self, project_id: str, path: str, content: str) -> WorkspaceDocument:
        target = self._safe_project_path(project_id, path)
        if not isinstance(content, str):
            raise TypeError("Document content must be text")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(target, content)
        self.update_project(project_id)
        return self._document_metadata(project_id, target)

    def read_document(self, project_id: str, path: str) -> str:
        target = self._safe_project_path(project_id, path)
        if not target.is_file():
            raise FileNotFoundError(path)
        return target.read_text(encoding="utf-8")

    def delete_document(self, project_id: str, path: str) -> bool:
        target = self._safe_project_path(project_id, path)
        if not target.is_file():
            return False
        target.unlink()
        self.update_project(project_id)
        return True

    def list_documents(self, project_id: str) -> List[WorkspaceDocument]:
        root = self._project_root(project_id)
        if not root.exists():
            raise KeyError(project_id)
        result = []
        for path in root.rglob("*"):
            if path.is_file():
                result.append(self._document_metadata(project_id, path))
        return sorted(result, key=lambda x: x.path)

    def search(self, query: str, project_id: Optional[str] = None, limit: int = 50) -> List[WorkspaceSearchResult]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Search query is required")
        if limit < 1:
            raise ValueError("Limit must be positive")
        projects = [self.get_project(project_id)] if project_id else self.list_projects()
        results = []
        needle = query.casefold()
        for project in projects:
            if project is None:
                continue
            for doc in self.list_documents(project.project_id):
                try:
                    text = self.read_document(project.project_id, doc.path)
                except (UnicodeDecodeError, OSError):
                    continue
                for number, line in enumerate(text.splitlines(), 1):
                    if needle in line.casefold():
                        results.append(WorkspaceSearchResult(project.project_id, doc.path, number, line))
                        if len(results) >= limit:
                            return results
        return results

    def snapshot(self, name: Optional[str] = None) -> Path:
        """Create a read-only copy of workspace contents for recovery."""
        safe_name = (name or time.strftime("snapshot-%Y%m%d-%H%M%S")).strip()
        self._validate_id(safe_name)
        snapshot_root = self.root / "snapshots" / safe_name
        if snapshot_root.exists():
            raise FileExistsError(safe_name)
        snapshot_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.root, snapshot_root, ignore=shutil.ignore_patterns("snapshots"))
        return snapshot_root

    def _document_metadata(self, project_id: str, path: Path) -> WorkspaceDocument:
        root = self._project_root(project_id)
        rel = path.relative_to(root).as_posix()
        kind = "text"
        try:
            path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            kind = "binary"
        stat = path.stat()
        return WorkspaceDocument(project_id, rel, stat.st_size, stat.st_mtime, kind)
