"""Transactional in-place updater for Alice.

The updater is deliberately standard-library-only so it can update an existing
Alice installation without installing a second copy or depending on the target
application's third-party packages.

Safety properties:
- never overwrites protected user data (.env, workspace, runtime state, backups)
- stages and verifies the package before touching the live installation
- backs up every overwritten file and records newly-created files
- runs the target installation's full pytest suite after applying the update
- restores the exact previous state if verification fails
- refuses silent downgrades unless explicitly allowed
- never deletes files during a normal update
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import time
import re
from pathlib import Path
from typing import Iterable

PROTECTED_EXACT = {
    ".env",
    ".alice_backups",
    "alice_workspace",
    "data",
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
}
PROTECTED_SUBTREES = {
    "alice/security",
    "alice/alice/security",
    "alice/permissions",
    "alice/device_consent",
}
MANIFEST_NAME = "upgrade_manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def version_tuple(value: str) -> tuple[int, ...]:
    text = str(value).strip().lower().lstrip("v")
    parts = []
    for part in text.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts or [0])


def read_version(root: Path) -> str:
    p = root / "VERSION.txt"
    if not p.exists():
        return "0.0"
    return p.read_text(encoding="utf-8").strip().splitlines()[0]


def is_protected(rel: str) -> bool:
    p = Path(rel.replace("\\", "/"))
    if not p.parts:
        return True
    if p.parts[0] in PROTECTED_EXACT:
        return True
    norm = p.as_posix()
    return any(norm == root or norm.startswith(root + "/") for root in PROTECTED_SUBTREES)


def iter_payload_files(payload: Path) -> Iterable[Path]:
    for p in payload.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(payload).as_posix()
        if rel == MANIFEST_NAME or rel.startswith("__pycache__/") or rel.endswith(".pyc"):
            continue
        if is_protected(rel):
            continue
        yield p


def build_manifest(payload: Path, version: str, base_version: str) -> dict:
    files = []
    for p in sorted(iter_payload_files(payload), key=lambda x: x.relative_to(payload).as_posix()):
        rel = p.relative_to(payload).as_posix()
        files.append({"path": rel, "sha256": sha256_file(p), "size": p.stat().st_size})
    return {
        "format": 1,
        "product": "ALICE",
        "version": version,
        "base_version": base_version,
        "files": files,
        "deletions": [],
        "protected": sorted(PROTECTED_EXACT | PROTECTED_SUBTREES),
    }


class UpgradeError(RuntimeError):
    pass


def _assert_no_reparse_path(path: Path) -> None:
    absolute = Path(path).absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            if not current.exists() and not current.is_symlink():
                continue
            info = current.lstat()
            attrs = getattr(info, "st_file_attributes", 0)
            if current.is_symlink() or getattr(current, "is_junction", lambda: False)() or attrs & 0x400:
                raise UpgradeError(f"Updater trust path contains a symlink or reparse point: {current}")
        except FileNotFoundError:
            continue


def _harden_directory(path: Path) -> None:
    """Restrict a new updater staging/backup directory to the current user and OS."""
    if os.name == "nt":
        import getpass
        domain = os.environ.get("USERDOMAIN", "")
        username = os.environ.get("USERNAME") or getpass.getuser()
        account = f"{domain}\\{username}" if domain else username
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r",
             f"{account}:(OI)(CI)F", "SYSTEM:(OI)(CI)F", "BUILTIN\\Administrators:(OI)(CI)F"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode:
            raise UpgradeError("Could not restrict updater staging ACLs with icacls")
    else:
        path.chmod(0o700)


def _secure_temp_dir(parent: Path, prefix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse_path(parent)
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    try:
        _assert_no_reparse_path(path)
        _harden_directory(path)
        return path
    except Exception:
        shutil.rmtree(path, ignore_errors=True)
        raise


class InPlaceUpdater:
    """Apply a signed-by-content, test-gated delta package to an installation."""

    def __init__(self, install_root: str | Path):
        requested = Path(install_root).expanduser().absolute()
        _assert_no_reparse_path(requested)
        self.root = requested.resolve()
        self.backup_root = self.root / ".alice_backups"

    def validate_install(self) -> dict:
        checks = {
            "root_exists": self.root.is_dir(),
            "alice_package": (self.root / "alice").is_dir(),
            "version_file": (self.root / "VERSION.txt").is_file(),
            "python": (self.root / ".venv" / "Scripts" / "python.exe").is_file()
            or (self.root / ".venv" / "bin" / "python").is_file(),
        }
        return {"ok": all(checks.values()), "checks": checks, "version": read_version(self.root)}

    @staticmethod
    def _safe_extract_zip(zip_path: Path, stage: Path) -> None:
        with zipfile.ZipFile(zip_path) as z:
            for info in z.infolist():
                name=info.filename.replace("\\","/")
                rel=Path(name)
                if not name or rel.is_absolute() or ".." in rel.parts:
                    raise UpgradeError(f"Unsafe ZIP member path: {name}")
                # ZIP Unix mode: reject symbolic links and special files.
                mode=(info.external_attr >> 16) & 0o170000
                if mode and mode != 0o100000 and not name.endswith("/"):
                    raise UpgradeError(f"Unsafe ZIP member type: {name}")
                target=stage/rel
                if name.endswith("/"):
                    target.mkdir(parents=True,exist_ok=True); continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(info,"r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src,dst)

    def validate_package(self, payload: str | Path) -> dict:
        payload = Path(payload).expanduser().resolve()
        if payload.is_file() and payload.suffix.lower() == ".zip":
            stage = _secure_temp_dir(self.backup_root, "stage_validate_")
            try:
                self._safe_extract_zip(payload,stage)
                result = self.validate_package(stage)
                result["package_zip"] = str(payload)
                return result
            except Exception:
                shutil.rmtree(stage,ignore_errors=True)
                raise
        manifest_path = payload / MANIFEST_NAME
        if not manifest_path.exists():
            raise UpgradeError(f"Missing {MANIFEST_NAME}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise UpgradeError(f"Invalid upgrade manifest: {exc}") from exc
        if manifest.get("product") != "ALICE" or manifest.get("format") != 1:
            raise UpgradeError("Unsupported Alice upgrade package")
        target = str(manifest.get("version", "")).strip()
        minimum = str(manifest.get("minimum_version", "0.0")).strip()
        if not target:
            raise UpgradeError("Upgrade package has no target version")
        if minimum and version_tuple(read_version(self.root)) < version_tuple(minimum):
            raise UpgradeError(f"This upgrade requires Alice {minimum} or newer; installed {read_version(self.root)}")
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise UpgradeError("Upgrade package contains no files")
        seen = set()
        for item in files:
            rel = Path(str(item.get("path", "")).replace("\\", "/"))
            rel_text = rel.as_posix()
            if not rel_text or rel.is_absolute() or ".." in rel.parts:
                raise UpgradeError(f"Unsafe package path: {rel_text}")
            if rel_text in seen:
                raise UpgradeError(f"Duplicate package path: {rel_text}")
            seen.add(rel_text)
            if is_protected(rel_text):
                raise UpgradeError(f"Package attempts to modify protected path: {rel_text}")
            source = payload / rel
            if not source.is_file():
                raise UpgradeError(f"Package file missing: {rel_text}")
            expected = str(item.get("sha256", ""))
            if len(expected) != 64 or sha256_file(source) != expected:
                raise UpgradeError(f"Hash mismatch: {rel_text}")
        deletions = manifest.get("deletions", [])
        if deletions:
            raise UpgradeError("Normal upgrades may not delete files; use a separately reviewed migration")
        return {"payload": str(payload), "manifest": manifest, "file_count": len(files)}

    def _backup_path(self) -> Path:
        stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns() % 1_000_000:06d}"
        dest = _secure_temp_dir(self.backup_root, f"inplace_{stamp}_")
        (dest / "files").mkdir()
        return dest

    def _snapshot_protected_state(self, backup: Path) -> dict:
        """Snapshot protected user configuration before an in-place upgrade.

        The normal manifest never overwrites .env, but we also snapshot and
        verify it explicitly so a launcher/installer regression cannot silently
        replace credentials with .env.example.
        """
        protected = backup / "protected"
        protected.mkdir(parents=True, exist_ok=True)
        env = self.root / ".env"
        result = {"env_exists": env.is_file(), "env_sha256": None, "env_backup": None}
        if env.is_file():
            dst = protected / ".env"
            shutil.copy2(env, dst)
            result["env_sha256"] = sha256_file(env)
            result["env_backup"] = str(dst)
        (protected / "state.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    def _verify_protected_state(self, snapshot: dict) -> None:
        env = self.root / ".env"
        if snapshot.get("env_exists"):
            if not env.is_file():
                raise UpgradeError("Protected .env disappeared during upgrade")
            actual = sha256_file(env)
            if actual != snapshot.get("env_sha256"):
                raise UpgradeError("Protected .env changed during upgrade; refusing to keep the update")

    def _backup_existing(self, rel_paths: list[str], backup: Path) -> dict:
        meta = {"root": str(self.root), "files": [], "created": []}
        for rel in rel_paths:
            target = self.root / rel
            if target.exists():
                if not target.is_file():
                    raise UpgradeError(f"Cannot overwrite non-file path: {rel}")
                dst = backup / "files" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, dst)
                meta["files"].append(rel)
            else:
                meta["created"].append(rel)
        (backup / "backup.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    def _target_python(self) -> str:
        win = self.root / ".venv" / "Scripts" / "python.exe"
        unix = self.root / ".venv" / "bin" / "python"
        if win.exists():
            return str(win)
        if unix.exists():
            return str(unix)
        return sys.executable

    def _run_tests(self) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        # Verification must be deterministic and independent of host/provider
        # configuration. Remove ALICE_* overrides just as the full installer
        # does; tests that need a provider/model setting set it explicitly.
        for name in list(env):
            if name.startswith("ALICE_"):
                env.pop(name, None)
        # The desktop process can also export provider settings that do not
        # use the ALICE_ prefix. In particular OPENROUTER_FREE_ONLY forces
        # every Router instance into a single-provider mode, causing tests
        # that intentionally remove API keys to fail in a user-dependent way.
        # The test suite configures provider behavior explicitly per test, so
        # remove inherited provider configuration and credentials here.
        for name in (
            "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
            "GEMINI_API_KEY", "GEMINI_MODEL",
            "LOCAL_AI_API_KEY", "LOCAL_AI_BASE_URL", "LOCAL_AI_MODEL",
            "OLLAMA_HOST",
            "OPENAI_API_KEY", "OPENAI_MODEL",
            "OPENROUTER_API_KEY", "OPENROUTER_FREE_ONLY", "OPENROUTER_MODEL",
        ):
            env.pop(name, None)
        # Never ask pytest to clear the installation cache. On Windows an
        # old cache entry can be locked by another process, causing pytest
        # to fail before a single test is collected.
        # Disabling the cache provider makes upgrade verification independent
        # of stale/locked .pytest_cache contents.
        verify_temp = _secure_temp_dir(self.backup_root, f"verify_tests_{time.time_ns()}_")
        old_env = {k: env.get(k) for k in ("PYTHONPATH", "PYTHON_DOTENV_DISABLED", "PYTEST_DISABLE_PLUGIN_AUTOLOAD")}
        env.pop("PYTHONPATH", None)
        env["PYTHON_DOTENV_DISABLED"] = "1"
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            return subprocess.run(
                [self._target_python(), "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp", str(verify_temp)],
                cwd=self.root,
                env=env,
                capture_output=True,
                text=True,
                timeout=240,
            )
        finally:
            # Pytest does not own a caller-supplied basetemp. Cleanup is best
            # effort because Windows can briefly hold a file after a test exits.
            for _ in range(5):
                try:
                    shutil.rmtree(verify_temp)
                    break
                except OSError:
                    time.sleep(0.25)

    def _copy_payload(self, payload: Path, files: list[dict]) -> list[str]:
        changed = []
        for item in files:
            rel = str(item["path"]).replace("\\", "/")
            source = payload / rel
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            changed.append(rel)
        return changed

    def _rollback(self, backup: Path) -> None:
        backup = Path(backup).expanduser().resolve()
        backup_root = self.backup_root.resolve()
        if backup.parent != backup_root:
            raise UpgradeError("Rollback backup is outside the installation backup root")
        try:
            meta = json.loads((backup / "backup.json").read_text(encoding="utf-8"))
        except Exception as exc:
            raise UpgradeError("Rollback backup metadata is missing or invalid") from exc
        if not isinstance(meta, dict) or Path(str(meta.get("root", ""))).resolve() != self.root:
            raise UpgradeError("Rollback backup belongs to a different installation")
        files = meta.get("files", [])
        created = meta.get("created", [])
        if not isinstance(files, list) or not isinstance(created, list):
            raise UpgradeError("Rollback backup file lists are invalid")

        def safe_path(raw):
            if not isinstance(raw, str):
                raise UpgradeError("Rollback backup contains a non-string path")
            normalized = raw.replace("\\", "/")
            rel = Path(normalized)
            if (not normalized or ":" in normalized or rel.is_absolute() or ".." in rel.parts
                    or any(part in ("", ".") for part in normalized.split("/")) or is_protected(normalized)):
                raise UpgradeError(f"Unsafe rollback backup path: {raw}")
            return normalized

        if len(set(files)) != len(files) or len(set(created)) != len(created):
            raise UpgradeError("Rollback backup contains duplicate paths")
        for raw in created:
            rel = safe_path(raw)
            target = self.root / rel
            if not target.resolve(strict=False).is_relative_to(self.root):
                raise UpgradeError("Rollback-created path escapes installation root")
            if target.exists() and target.is_file():
                target.unlink()
        for raw in files:
            rel = safe_path(raw)
            source = backup / "files" / rel
            target = self.root / rel
            if (not source.is_file() or not source.resolve().is_relative_to((backup / "files").resolve())
                    or not target.resolve(strict=False).is_relative_to(self.root)):
                raise UpgradeError(f"Rollback source or target is unsafe: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def apply(self, payload: str | Path, *, allow_downgrade: bool = False,
              expected_sha256: str | None = None, state_callback=None) -> dict:
        payload = Path(payload).expanduser().resolve()
        package_sha256 = sha256_file(payload) if payload.is_file() and payload.suffix.lower() == ".zip" else ""
        if expected_sha256 is not None and package_sha256 != str(expected_sha256).lower():
            raise UpgradeError("Update package changed after signature verification")
        install = self.validate_install()
        if not install["ok"]:
            raise UpgradeError("Target is not a valid Alice installation: " + json.dumps(install["checks"]))
        cleanup_stage = None
        if payload.is_file() and payload.suffix.lower() == ".zip":
            cleanup_stage = _secure_temp_dir(self.backup_root, "stage_apply_")
            try:
                self._safe_extract_zip(payload,cleanup_stage)
                if expected_sha256 is not None and sha256_file(payload) != str(expected_sha256).lower():
                    raise UpgradeError("Update package changed while it was being staged")
            except Exception:
                shutil.rmtree(cleanup_stage, ignore_errors=True)
                raise
            payload = cleanup_stage
        try:
            pkg = self.validate_package(payload)
            manifest = pkg["manifest"]
            provenance = manifest.get("provenance", {})
            promotion = provenance.get("promotion", {}) if isinstance(provenance, dict) else {}
            if isinstance(promotion, dict) and promotion.get("blocked_until_os_sandbox") is True:
                raise UpgradeError(
                    "This DEVOUR candidate cannot be installed until its generated code has passed "
                    "tests in an OS-level filesystem and network sandbox."
                )
            current = read_version(self.root)
            target = str(manifest["version"])
            if not allow_downgrade and version_tuple(target) <= version_tuple(current):
                raise UpgradeError(f"Refusing non-forward upgrade: installed {current}, package {target}")
            devour_install_context=[]
            if isinstance(provenance,dict) and provenance.get("kind")=="devour_native_reimplementation":
                if not package_sha256:
                    raise UpgradeError("DEVOUR candidate installation requires its exact ZIP package digest")
                verification=provenance.get("verification",{})
                sandbox=verification.get("sandbox",{}) if isinstance(verification,dict) else {}
                approval=provenance.get("user_approval",{})
                if (not isinstance(sandbox,dict) or sandbox.get("verified") is not True
                        or promotion.get("blocked_until_os_sandbox") is True
                        or not isinstance(approval,dict) or approval.get("per_capability") is not True):
                    raise UpgradeError("DEVOUR install requires isolated test evidence and per-capability approval")
                selected=provenance.get("selected_capabilities",[])
                approvals=approval.get("approvals",[])
                declared_entry_points=provenance.get("declared_entry_points")
                report_sha=str(approval.get("report_sha256", ""))
                tree_sha=str(approval.get("tree_sha256", ""))
                if (not isinstance(selected,list) or not selected or len(selected)>16
                        or not isinstance(approvals,list)
                        or not isinstance(declared_entry_points,dict)):
                    raise UpgradeError("DEVOUR install provenance is missing a bounded capability approval list")
                by_capability={str(row.get("capability","" )).strip().lower():row
                               for row in approvals if isinstance(row,dict)}
                # Read-only registry inspection occurs before any install mutation.
                from ..capabilities.manager import CapabilityManager
                from ..execution.callable_provenance import normalize_entry_point
                registry=CapabilityManager(self.root,initialize=False)
                normalized_selected={str(raw).strip().lower().replace(" ","_") for raw in selected}
                normalized_entry_points={str(key).strip().lower().replace(" ","_"):value
                                         for key,value in declared_entry_points.items()}
                if set(normalized_entry_points)!=normalized_selected:
                    raise UpgradeError("DEVOUR package must declare one runtime entry point for every selected capability")
                for raw_name in selected:
                    name=str(raw_name).strip().lower().replace(" ","_")
                    if not re.fullmatch(r"[a-z0-9_]{1,80}",name):
                        raise UpgradeError("DEVOUR install contains an invalid capability name")
                    approved=by_capability.get(name)
                    if not approved:
                        raise UpgradeError("DEVOUR install is missing its per-capability approval receipt")
                    entry_point=normalize_entry_point(normalized_entry_points.get(name))
                    if entry_point is None:
                        raise UpgradeError("DEVOUR package has an invalid declared runtime entry point")
                    cap_digest=str(approved.get("candidate_sha256", ""))
                    check=registry.validate_devour_candidate_installation(
                        name,candidate_version=target,package_sha256=package_sha256,
                        report_sha256=report_sha,tree_sha256=tree_sha,
                        capability_candidate_sha256=cap_digest,entry_point=entry_point)
                    if not check.get("ok"):
                        raise UpgradeError("DEVOUR install does not match the current isolated candidate receipt and entry point")
                    devour_install_context.append({"name":name,"capability_candidate_sha256":cap_digest,
                                                   "entry_point":entry_point})
            rel_paths = [str(x["path"]).replace("\\", "/") for x in manifest["files"]]
            backup = self._backup_path()
            self._backup_existing(rel_paths, backup)
            protected_snapshot = self._snapshot_protected_state(backup)
            try:
                if state_callback is not None:
                    state_callback("BACKED_UP", backup)
                    state_callback("APPLYING", backup)
                self._copy_payload(payload, manifest["files"])
                self._verify_protected_state(protected_snapshot)
                test = self._run_tests()
                if test.returncode:
                    self._rollback(backup)
                    return {
                        "ok": False, "rolled_back": True, "version": current, "target": target,
                        "backup": str(backup), "reason": "post_update_tests_failed",
                        "output": test.stderr or test.stdout,
                    }
                candidate_lifecycle=[]
                if devour_install_context:
                    from ..capabilities.manager import CapabilityManager
                    registry=CapabilityManager(self.root)
                    backup_manifest_sha256=sha256_file(backup/"backup.json")
                    approval=provenance.get("user_approval",{})
                    for entry in devour_install_context:
                        try:
                            lifecycle=registry.record_devour_installation(
                                entry["name"],candidate_version=target,
                                package_sha256=package_sha256,
                                report_sha256=approval.get("report_sha256"),
                                tree_sha256=approval.get("tree_sha256"),
                                capability_candidate_sha256=entry["capability_candidate_sha256"],
                                test_summary=test.stdout.strip(),
                                rollback_backup_sha256=backup_manifest_sha256,
                                installed_artifacts=manifest.get("files"))
                        except Exception as exc:
                            lifecycle={"recorded":False,"active":False,"verified":False,
                                       "status":"installed_pending_registry_receipt",
                                       "error_class":type(exc).__name__}
                        candidate_lifecycle.append({"name":entry["name"],**lifecycle})
                return {
                    "ok": True, "rolled_back": False, "version": read_version(self.root),
                    "previous_version": current, "backup": str(backup), "changed_files": rel_paths,
                    "protected_env_preserved": bool(protected_snapshot.get("env_exists")),
                    "candidate_lifecycle":candidate_lifecycle,
                    "tests": test.stdout.strip(),
                }
            except Exception:
                try:self._rollback(backup)
                finally:raise
        finally:
            if cleanup_stage is not None: shutil.rmtree(cleanup_stage, ignore_errors=True)

    def rollback(self, backup: str | Path) -> dict:
        backup = Path(backup).expanduser().resolve()
        if backup.parent != self.backup_root.resolve() or not (backup / "backup.json").exists():
            raise UpgradeError("Backup is outside Alice's backup directory or is invalid")
        before = read_version(self.root)
        self._rollback(backup)
        return {"ok": True, "from_version": before, "version": read_version(self.root), "backup": str(backup)}


def discover_installation(candidates: Iterable[str | Path] | None = None) -> Path | None:
    """Find the user's existing Alice installation without guessing arbitrary folders."""
    roots = []
    env_root = os.getenv("ALICE_ROOT")
    if env_root:
        roots.append(Path(env_root))
    if candidates:
        roots.extend(Path(x) for x in candidates)
    home = Path.home()
    roots.extend([Path("C:/Alice"), home / "Alice"])
    # If called from an extracted upgrade utility, don't treat the payload itself as an install.
    here = Path(__file__).resolve()
    for p in [here.parent.parent.parent, here.parent.parent.parent.parent, Path.cwd()]:
        roots.append(p)
    seen = set()
    for root in roots:
        try:
            root = root.expanduser().resolve()
        except Exception:
            continue
        if root in seen:
            continue
        seen.add(root)
        if (root / "alice").is_dir() and (root / "VERSION.txt").is_file():
            return root
    return None
