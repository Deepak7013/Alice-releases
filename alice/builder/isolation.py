"""Run generated Python project tests in ALICE's verified Docker sandbox."""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..maintenance.candidate_container import DockerCandidateRunner


class DockerBuilderTestRunner:
    """Allow pytest only, on a disposable source copy, with networkless isolation."""

    _FLAGS = {"-q", "--quiet", "-x", "--exitfirst", "--disable-warnings"}
    _OMIT_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}

    def __init__(self, runner: DockerCandidateRunner | None = None, timeout: int = 240):
        self.runner = runner or DockerCandidateRunner()
        self.timeout = max(1, min(int(timeout), 600))

    @classmethod
    def _test_paths(cls, project: Path, command: str) -> tuple[str, ...]:
        try:
            words = shlex.split(str(command), posix=True)
        except ValueError as exc:
            raise ValueError("Malformed test command") from exc
        if not words:
            raise ValueError("Empty test command")
        first = Path(words[0]).name.casefold()
        if first in {"python", "python3", "python.exe", "python3.exe"}:
            if len(words) < 3 or words[1:3] != ["-m", "pytest"]:
                raise ValueError("Isolated builder accepts only Python pytest commands")
            words = words[3:]
        elif first in {"pytest", "pytest.exe", "py.test"}:
            words = words[1:]
        else:
            raise ValueError("Isolated builder accepts only pytest commands")

        paths = []
        for item in words:
            if item in cls._FLAGS:
                continue
            if item.startswith("--maxfail=") and item.partition("=")[2].isdigit():
                continue
            if item.startswith("-"):
                raise ValueError("Unsupported pytest option in isolated builder command")
            rel = Path(item.replace("\\", "/"))
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("Test path escapes generated project")
            target = project / rel
            probe = project
            for part in rel.parts:
                probe = probe / part
                if probe.is_symlink():
                    raise ValueError("Generated test path traverses a symbolic link")
            resolved = target.resolve()
            if project.resolve() not in resolved.parents and resolved != project.resolve():
                raise ValueError("Test path escapes generated project")
            if not resolved.exists() or not (resolved.is_file() or resolved.is_dir()):
                raise ValueError("Requested pytest path is missing")
            paths.append(rel.as_posix())
        return tuple(paths)

    @classmethod
    def _copy_project(cls, project: Path, stage: Path) -> None:
        for current, directories, files in os.walk(project, followlinks=False):
            current_path = Path(current)
            directories[:] = [name for name in directories if name.casefold() not in cls._OMIT_DIRS]
            for name in list(directories):
                if (current_path / name).is_symlink():
                    raise ValueError("Generated project contains a symlink")
            for name in files:
                source = current_path / name
                lower = name.casefold()
                if lower in {".env", ".env.local", ".env.production", ".env.development"}:
                    continue
                if lower.endswith((".pem", ".key", ".p12", ".pfx")):
                    continue
                if source.is_symlink():
                    raise ValueError("Generated project contains a symlink")
                relative = source.relative_to(project)
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    @staticmethod
    def _failed(message: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.CompletedProcess(["docker"], 125, "", message)
        result.sandbox_evidence = {"verified": False, "reason": message[:500]}
        return result

    def run(self, project: str | Path, command: str) -> subprocess.CompletedProcess[str]:
        root = Path(project).resolve(strict=True)
        if not root.is_dir():
            return self._failed("Generated project is not a directory")
        try:
            paths = self._test_paths(root, command)
            with tempfile.TemporaryDirectory(prefix="alice-builder-test-") as temporary:
                stage = Path(temporary) / "project"
                stage.mkdir()
                self._copy_project(root, stage)
                # DockerCandidateRunner independently verifies daemon, image and container restrictions.
                result = self.runner.run_tests(stage, timeout=self.timeout, test_paths=paths)
                evidence = getattr(result, "sandbox_evidence", {})
                result.sandbox_evidence = {
                    **(evidence if isinstance(evidence, dict) else {}),
                    "generated_project_copy_only": True,
                    "command_type": "pytest",
                    "project_files_writable_to_test": False,
                }
                return result
        except (OSError, ValueError, RuntimeError) as exc:
            return self._failed(f"Isolated builder test rejected: {type(exc).__name__}: {exc}")
