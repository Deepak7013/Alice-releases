"""Bounded local input adapters for DEVOUR's quarantine pipeline.

Supported inputs are local trees, individual regular files, ZIP-compatible
packages (including JAR/APK containers), and TAR archives. Unknown file types
are retained for fingerprinting and are reported as metadata-only unless a
static content adapter exists. Archive members are copied explicitly; archive
extraction helpers are never used on untrusted input.
"""
from __future__ import annotations

import hashlib
import os
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class IntakeError(ValueError):
    pass


@dataclass(frozen=True)
class IntakeResult:
    source: Path
    method: str
    input_format: str
    files_copied: int
    bytes_copied: int
    input_sha256: str = ""
    source_size: int = 0


class LocalInputAdapter:
    """Stage local DEVOUR inputs with traversal, link, and size limits."""

    SUPPORTED_SUFFIXES = {
        ".py", ".pyi", ".rs", ".toml", ".js", ".ts", ".tsx", ".jsx",
        ".go", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs",
        ".rb", ".php", ".swift", ".md", ".rst", ".txt", ".json",
        ".yaml", ".yml", ".xml", ".html", ".css", ".sh", ".ps1",
        ".bat", ".lock", ".cfg", ".ini", ".mod", ".csproj", ".dart",
        ".lua", ".scala", ".sc", ".pl", ".r", ".jl", ".ex", ".exs",
        ".hs", ".lhs", ".clj", ".cljs", ".cljc", ".vue", ".svelte",
        ".proto", ".graphql", ".gql", ".gradle", ".kts", ".properties",
        ".ipynb", ".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp",
    }
    IGNORED_DIRS = {
        ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
        "node_modules", "alice_workspace", ".aws", ".ssh", ".gnupg", ".azure",
    }
    SENSITIVE_NAMES = {
        ".env", "credentials.json", "service-account.json", "id_rsa",
        "id_ed25519", "secrets.json", ".npmrc", ".pypirc", ".netrc",
        "authorized_keys", "known_hosts",
    }
    CHUNK_BYTES = 1024 * 1024

    def __init__(self, *, max_files=12000, max_total_bytes=250_000_000):
        self.max_files = int(max_files)
        self.max_total_bytes = int(max_total_bytes)
        if self.max_files <= 0 or self.max_total_bytes <= 0:
            raise ValueError("DEVOUR intake limits must be positive")

    @staticmethod
    def _relative_parts(name: str) -> tuple[str, ...]:
        normalized = str(name).replace("\\", "/")
        path = PurePosixPath(normalized)
        parts = path.parts
        if (not normalized or path.is_absolute() or not parts
                or any(part in {"..", ""} for part in parts)
                or any(":" in part for part in parts)):
            raise IntakeError(f"Unsafe archive path rejected: {name!r}")
        return parts

    @classmethod
    def _target(cls, destination: Path, name: str) -> Path:
        parts = cls._relative_parts(name)
        target = destination.joinpath(*parts).resolve()
        root = destination.resolve()
        if target != root and root not in target.parents:
            raise IntakeError(f"Archive path escapes quarantine: {name!r}")
        return target

    @classmethod
    def _is_sensitive(cls, path: Path) -> bool:
        name = path.name.casefold()
        return (name in cls.SENSITIVE_NAMES or name.startswith((".env.", "secret", "credential"))
                or name.endswith((".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")))

    @classmethod
    def _ignored_parts(cls, parts):
        return any(str(part).casefold() in cls.IGNORED_DIRS for part in parts)

    def _copy_file(self, source, target, *, remaining, expected_size=None):
        target.parent.mkdir(parents=True, exist_ok=True)
        copied = 0
        with source, target.open("xb") as out:
            while True:
                block = source.read(self.CHUNK_BYTES)
                if not block:
                    break
                copied += len(block)
                if copied > remaining:
                    raise IntakeError("Input exceeds DEVOUR's total quarantine size limit.")
                out.write(block)
        if expected_size is not None and copied != expected_size:
            raise IntakeError("Archive member size did not match its directory metadata.")
        return copied

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(LocalInputAdapter.CHUNK_BYTES), b""):
                digest.update(block)
        return digest.hexdigest()

    @classmethod
    def _format_for_file(cls, path: Path) -> str:
        suffix = path.suffix.casefold()
        if suffix == ".jar":
            return "jar"
        if suffix == ".apk":
            return "apk"
        if suffix:
            return suffix.lstrip(".") if suffix in cls.SUPPORTED_SUFFIXES else f"opaque:{suffix.lstrip('.')}"
        return "opaque:no_extension"

    def _stage_directory(self, source: Path, destination: Path) -> IntakeResult:
        copied_files = copied_bytes = 0
        for current, directories, filenames in os.walk(source, topdown=True, followlinks=False):
            current_path = Path(current)
            kept = []
            for name in directories:
                child = current_path / name
                if name.casefold() in self.IGNORED_DIRS:
                    continue
                if child.is_symlink():
                    raise IntakeError(f"Symbolic-link directory rejected: {child.relative_to(source)}")
                kept.append(name)
            directories[:] = kept
            for name in filenames:
                item = current_path / name
                if item.is_symlink():
                    raise IntakeError(f"Symbolic-link file rejected: {item.relative_to(source)}")
                if self._is_sensitive(item):
                    continue
                item_stat = item.stat(follow_symlinks=False)
                if not stat.S_ISREG(item_stat.st_mode):
                    raise IntakeError(f"Non-regular source file rejected: {item.relative_to(source)}")
                size = item_stat.st_size
                copied_files += 1
                if copied_files > self.max_files or copied_bytes + size > self.max_total_bytes:
                    raise IntakeError("Directory exceeds DEVOUR's quarantine limits.")
                relative = item.relative_to(source)
                target = destination / relative
                with item.open("rb") as stream:
                    copied_bytes += self._copy_file(
                        stream, target, remaining=self.max_total_bytes - copied_bytes,
                        expected_size=size,
                    )
        return IntakeResult(destination, "local_directory", "directory", copied_files, copied_bytes)

    def _stage_zip(self, archive_path: Path, destination: Path, input_format="zip") -> IntakeResult:
        copied_files = copied_bytes = 0
        seen = set()
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > self.max_files * 2:
                raise IntakeError("ZIP contains too many archive entries.")
            declared = sum(info.file_size for info in members if not info.is_dir())
            if declared > self.max_total_bytes:
                raise IntakeError("ZIP exceeds DEVOUR's quarantine size limit.")
            for info in members:
                parts=self._relative_parts(info.filename.rstrip("/"))
                target=self._target(destination,info.filename.rstrip("/"))
                key = str(target).casefold()
                if key in seen:
                    raise IntakeError(f"Duplicate archive path rejected: {info.filename!r}")
                seen.add(key)
                if self._ignored_parts(parts):
                    continue
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if stat.S_ISLNK(mode) or file_type not in {0, stat.S_IFREG}:
                    raise IntakeError(f"Non-regular ZIP member rejected: {info.filename!r}")
                if info.flag_bits & 1:
                    raise IntakeError("Encrypted ZIP members are not supported.")
                if self._is_sensitive(target):
                    continue
                copied_files += 1
                if copied_files > self.max_files:
                    raise IntakeError("ZIP contains too many files for one DEVOUR pass.")
                with archive.open(info, "r") as stream:
                    copied_bytes += self._copy_file(
                        stream, target, remaining=self.max_total_bytes - copied_bytes,
                        expected_size=info.file_size,
                    )
        return IntakeResult(destination, "local_zip", input_format, copied_files, copied_bytes)

    def _stage_tar(self, archive_path: Path, destination: Path) -> IntakeResult:
        copied_files = copied_bytes = 0
        seen = set()
        with tarfile.open(archive_path, mode="r:*") as archive:
            members = archive.getmembers()
            if len(members) > self.max_files * 2:
                raise IntakeError("TAR contains too many archive entries.")
            declared = 0
            for member in members:
                if not (member.isdir() or member.isfile()):
                    raise IntakeError(f"Non-regular TAR member rejected: {member.name!r}")
                if member.isfile():
                    declared += member.size
            if declared > self.max_total_bytes:
                raise IntakeError("TAR exceeds DEVOUR's quarantine size limit.")
            for member in members:
                parts=self._relative_parts(member.name.rstrip("/"))
                target=self._target(destination,member.name.rstrip("/"))
                key = str(target).casefold()
                if key in seen:
                    raise IntakeError(f"Duplicate archive path rejected: {member.name!r}")
                seen.add(key)
                if self._ignored_parts(parts):
                    continue
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if self._is_sensitive(target):
                    continue
                copied_files += 1
                if copied_files > self.max_files:
                    raise IntakeError("TAR contains too many files for one DEVOUR pass.")
                stream = archive.extractfile(member)
                if stream is None:
                    raise IntakeError(f"TAR member could not be read: {member.name!r}")
                copied_bytes += self._copy_file(
                    stream, target, remaining=self.max_total_bytes - copied_bytes,
                    expected_size=member.size,
                )
        return IntakeResult(destination, "local_tar", "tar", copied_files, copied_bytes)

    def stage(self, raw_source, work: Path) -> IntakeResult:
        original = Path(raw_source).expanduser()
        if original.is_symlink():
            raise IntakeError("Symbolic-link input roots are not accepted.")
        source = original.resolve()
        if not source.exists():
            raise IntakeError(f"Source not found: {source}")
        destination = work / "source"
        destination.mkdir(parents=True, exist_ok=False)
        if source.is_dir():
            return self._stage_directory(source, destination)
        if not source.is_file():
            raise IntakeError("DEVOUR input must be a regular file, directory, or supported archive.")
        if self._is_sensitive(source):
            raise IntakeError("Credential and private-key files are not accepted as DEVOUR input.")
        suffix = source.suffix.casefold()
        lower_name = source.name.casefold()
        if zipfile.is_zipfile(source):
            archive_format = "jar" if suffix == ".jar" else "apk" if suffix == ".apk" else "zip"
            staged = self._stage_zip(source, destination, archive_format)
            return IntakeResult(staged.source, staged.method, staged.input_format,
                                staged.files_copied, staged.bytes_copied,
                                self._sha256_file(source), source.stat().st_size)
        if suffix in {".zip", ".jar", ".apk"}:
            raise IntakeError(f"File is not a valid {suffix.lstrip('.').upper()} archive.")
        if suffix in {".tar", ".tgz"} or lower_name.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
            return self._stage_tar(source, destination)
        size = source.stat().st_size
        if size > self.max_total_bytes:
            raise IntakeError("File exceeds DEVOUR's quarantine size limit.")
        target = destination / source.name
        with source.open("rb") as stream:
            copied = self._copy_file(stream, target, remaining=self.max_total_bytes, expected_size=size)
        return IntakeResult(destination, "local_file", self._format_for_file(source), 1, copied,
                            self._sha256_file(source), size)
