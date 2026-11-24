"""Transactional self-diagnostics and governed self-upgrades.

Self-upgrades are staged outside the live source tree, syntax-checked, tested with
the complete Alice suite, and promoted only when every gate passes. A failed
candidate is discarded and the live installation remains unchanged.
"""
from __future__ import annotations
import ast, hashlib, json, keyword, os, shutil, subprocess, tempfile, time, zipfile
from pathlib import Path
from ..engineering.gate import SelfEngineeringGate
from ..deployment.updater import build_manifest, read_version, version_tuple
from ..security.ingest_guard import IngestGuard
from ..execution.callable_provenance import normalize_entry_point
from .candidate_container import DockerCandidateRunner

PROTECTED_PARTS = {
    ".git", ".alice_backups", ".env", "credentials.json", "secrets.json",
    "security", "permissions", "device_consent",
}
PROTECTED_FILES = {"__init__.py"}  # package initializers are preserved by default

class SelfManager:
    MAX_FILES = 24
    MAX_FILE_BYTES = 300_000
    MAX_DEVOUR_REPORT_BYTES = 4_000_000
    TEST_TIMEOUT = 180
    PROTECTED_ROOTS = ("alice/security", "alice/permissions", "alice/device_consent")

    def __init__(self, root=None, router=None, candidate_runner=None, capability_manager=None):
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.router = router
        self.candidate_runner = candidate_runner or DockerCandidateRunner()
        self.capability_manager = capability_manager
        self.engineering_gate = SelfEngineeringGate()
        self.backups = self.root / ".alice_backups"
        self.backups.mkdir(exist_ok=True)

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def _is_protected(self, rel: str) -> bool:
        p = Path(rel)
        return (
            p.name in PROTECTED_FILES
            or any(part.lower() in PROTECTED_PARTS for part in p.parts)
            or rel in self.PROTECTED_ROOTS
            or any(rel.startswith(x + "/") for x in self.PROTECTED_ROOTS)
        )

    def read_source(self, rel):
        """Read a non-protected ALICE source file for self-inspection."""
        rel=str(rel).replace("\\","/")
        p=(self.root/rel).resolve()
        if not rel.startswith("alice/") or self._is_protected(rel):
            raise ValueError("Self-inspection is limited to non-protected alice/ source files")
        if self.root not in p.parents or not p.is_file():
            raise ValueError("Source file not found")
        text=p.read_text(encoding="utf-8")
        return {"ok":True,"path":rel,"bytes":len(text.encode("utf-8")),"content":text}

    def source_inventory(self, query=""):
        q=str(query or "").lower().strip()
        rows=[]
        for p in (self.root/"alice").rglob("*.py"):
            rel=self._relative(p)
            if self._is_protected(rel): continue
            if q and q not in rel.lower(): continue
            rows.append({"path":rel,"bytes":p.stat().st_size})
        return {"ok":True,"count":len(rows),"files":rows[:1000]}

    def workspace_status(self):
        """Expose safe metadata about Alice's durable state without secrets."""
        paths=["alice_workspace/memory.json","alice_workspace/runtime","alice_workspace/gluttony",
               "alice_workspace/conversations","alice_workspace/rendered_artifacts"]
        out=[]
        for rel in paths:
            p=self.root/rel
            if p.exists():
                if p.is_file(): size=p.stat().st_size
                else:
                    size=sum(x.stat().st_size for x in p.rglob("*") if x.is_file())
                out.append({"path":rel,"exists":True,"size_bytes":size})
            else: out.append({"path":rel,"exists":False,"size_bytes":0})
        return {"ok":True,"state":out}

    def diagnostics(self):
        errors = []
        py_files = list((self.root / "alice").rglob("*.py"))
        for p in py_files:
            try:
                ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            except Exception as e:
                errors.append({"file": self._relative(p), "error": str(e)})
        test = self.run_tests() if not errors else None
        if test and test.returncode:
            errors.append({"file": "pytest", "error": test.stderr or test.stdout})
        return {
            "ok": not errors,
            "python_files": len(py_files),
            "tests": "full_suite" if test is not None else "skipped",
            "errors": errors,
        }

    def snapshot(self):
        stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns()%1_000_000:06d}"
        dest = self.backups / stamp
        shutil.copytree(
            self.root, dest,
            ignore=shutil.ignore_patterns(
                ".venv", ".git", ".alice_backups", "__pycache__", ".pytest_cache"
            ),
        )
        return str(dest)

    def restore(self, backup):
        src = Path(backup).resolve()
        if src.parent != self.backups.resolve():
            raise ValueError("Backup outside Alice backup directory")
        # Restore only tracked project contents; never delete the backup store.
        for p in list(self.root.iterdir()):
            if p.name == ".alice_backups":
                continue
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
        for p in src.iterdir():
            target = self.root / p.name
            if p.is_dir():
                shutil.copytree(p, target)
            else:
                shutil.copy2(p, target)
        return True

    def run_tests(self, cwd=None, *, test_paths=None):
        test_cwd = Path(cwd or self.root).resolve()
        if test_cwd != self.root:
            # Never execute generated candidate code in the ALICE host process.
            # A missing Docker engine/image or a weaker container configuration
            # returns a failure; there is deliberately no host-process fallback.
            return self.candidate_runner.run_tests(
                test_cwd, timeout=self.TEST_TIMEOUT + 60, test_paths=test_paths,
            )
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [os.sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=test_cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=self.TEST_TIMEOUT,
        )

    def _validate_items(self, items):
        if not isinstance(items, list) or not items or len(items) > self.MAX_FILES:
            raise ValueError("Upgrade must contain a bounded non-empty list of files")
        seen = set()
        for item in items:
            if not isinstance(item, dict) or not item.get("path") or "content" not in item:
                raise ValueError("Each change needs path and content")
            rel = Path(str(item["path"]).replace("\\", "/"))
            rel_text = rel.as_posix()
            if rel.is_absolute() or ".." in rel.parts or not rel_text.startswith("alice/"):
                raise ValueError("Changes may only modify alice/ files")
            if rel_text in seen:
                raise ValueError("Duplicate file in upgrade")
            seen.add(rel_text)
            if self._is_protected(rel_text):
                raise ValueError(f"protected path: {rel_text}")
            content = item["content"]
            if not isinstance(content, str):
                raise ValueError("File content must be text")
            if len(content.encode("utf-8")) > self.MAX_FILE_BYTES:
                raise ValueError("File change is too large")
            if rel.suffix == ".py":
                ast.parse(content, filename=rel_text)
        return sorted(seen)

    def _copy_tree_for_stage(self):
        stage = Path(tempfile.mkdtemp(prefix="alice_upgrade_"))
        ignored_dirs = {
            ".git", ".alice_backups", ".venv", "venv", "node_modules",
            "__pycache__", ".pytest_cache", "alice_workspace", "releases",
            "backups", "dist", "build", ".aws", ".azure", ".ssh", ".gnupg",
        }
        sensitive_names = {
            "credentials.json", "secrets.json", "service-account.json",
            ".netrc", ".npmrc", ".pypirc", "id_rsa", "id_ed25519",
        }

        def ignore_private_state(directory, names):
            ignored = []
            for name in names:
                lowered = name.casefold()
                if (lowered in ignored_dirs or lowered in sensitive_names
                        or lowered == ".env"
                        or (lowered.startswith(".env.") and lowered not in {
                            ".env.example", ".env.template", ".env.sample",
                        })
                        or lowered.startswith(("secret", "credential"))
                        or lowered.endswith((".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"))):
                    ignored.append(name)
            return ignored

        shutil.copytree(
            self.root, stage, dirs_exist_ok=True,
            ignore=ignore_private_state,
        )
        return stage

    def _apply_items(self, stage, items):
        for item in items:
            target = (stage / Path(item["path"])).resolve()
            if stage not in target.parents:
                raise ValueError("staged target escaped stage root")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item["content"].encode("utf-8"))

    @staticmethod
    def _hash_file(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _safety_invariants(self):
        invariants = {}
        for rel in self.PROTECTED_ROOTS:
            root = self.root / rel
            if root.exists():
                for p in root.rglob("*"):
                    if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                        invariants[self._relative(p)] = self._hash_file(p)
        return invariants

    def _stage_test(self, stage):
        return self._stage_test_with_candidate_tests(stage)

    def _stage_test_with_candidate_tests(self, stage, candidate_tests=()):
        # Syntax/bytecode compilation is a fast first gate before the full suite.
        compile_result=self._compile_tree(stage)
        if compile_result.returncode:
            return compile_result
        focused = None
        if candidate_tests:
            focused = self.run_tests(cwd=stage, test_paths=tuple(candidate_tests))
            if focused.returncode:
                return focused
        # The candidate must pass the same complete suite as the live build.
        result = self.run_tests(cwd=stage)
        if result.returncode == 0 and focused is not None:
            result.candidate_test_paths = list(candidate_tests)
            result.candidate_test_summary = str(focused.stdout or "").strip()[-2000:]
            result.candidate_test_sandbox_evidence = getattr(focused, "sandbox_evidence", None)
        return result

    def apply_patch(self, patch_text):
        items = json.loads(patch_text) if isinstance(patch_text, str) else patch_text
        changed = self._validate_items(items)
        impact = self.engineering_gate.preflight(self.root, items)
        backup = self.snapshot()
        before_invariants = self._safety_invariants()
        stage = self._copy_tree_for_stage()
        try:
            self._apply_items(stage, items)
            result = self._stage_test(stage)
            if result.returncode:
                return {
                    "ok": False, "rolled_back": False, "promoted": False,
                    "backup": backup, "changed": changed,
                    "reason": "candidate_tests_failed",
                    "impact": impact,
                    "output": result.stderr or result.stdout,
                }
            # Compare protected invariants before promotion.
            for rel, digest in before_invariants.items():
                candidate = stage / rel
                if not candidate.exists() or self._hash_file(candidate) != digest:
                    return {
                        "ok": False, "rolled_back": False, "promoted": False,
                        "backup": backup, "changed": changed,
                        "reason": f"protected_invariant_changed:{rel}",
                        "impact": impact,
                    }
            # Promote atomically-ish file-by-file only after all gates pass.
            self._promote_stage(stage)
            after = self.diagnostics()
            if not after["ok"]:
                self.restore(backup)
                return {
                    "ok": False, "rolled_back": True, "promoted": False,
                    "backup": backup, "changed": changed,
                    "reason": "post_promotion_diagnostics_failed",
                    "impact": impact,
                    "diagnostics": after,
                }
            return {
                "ok": True, "rolled_back": False, "promoted": True,
                "backup": backup, "changed": changed,
                "reason": "upgrade_verified_and_promoted",
                "impact": impact,
                "tests": result.stdout.strip(),
            }
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def _promote_stage(self, stage):
        # Keep files outside alice untouched; replace only the alice source tree.
        live_alice = self.root / "alice"
        staged_alice = stage / "alice"
        temp_live = self.root / f".alice_promote_{time.time_ns()}"
        shutil.copytree(staged_alice, temp_live)
        old_live = self.root / f".alice_old_{time.time_ns()}"
        live_alice.rename(old_live)
        try:
            temp_live.rename(live_alice)
            shutil.rmtree(old_live)
        except Exception:
            if live_alice.exists():
                shutil.rmtree(live_alice)
            old_live.rename(live_alice)
            raise


    def _next_version(self, current=None):
        """Return the next patch version without touching the live installation."""
        current = current or read_version(self.root)
        nums = list(version_tuple(current))
        while len(nums) < 3:
            nums.append(0)
        nums[-1] += 1
        return "ALICE v%d.%d.%d" % tuple(nums[:3])

    def _write_evolution_journal(self, entry):
        """Persist a compact audit trail outside the executable source tree."""
        path = self.root / "alice_workspace" / "runtime" / "self_upgrade_journal.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            if not isinstance(rows, list): rows = []
        except Exception:
            rows = []
        rows.append(entry)
        path.write_text(json.dumps(rows[-100:], indent=2, ensure_ascii=False), encoding="utf-8")

    def _package_candidate(self, stage, changed, base_version, *, provenance=None):
        """Create a local, content-hashed delta package from a verified candidate."""
        target_version = self._next_version(base_version)
        payload = Path(tempfile.mkdtemp(prefix="alice_self_package_"))
        try:
            for rel in changed:
                source = stage / rel
                if not source.is_file():
                    raise ValueError(f"Candidate file missing: {rel}")
                dest = payload / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
            # VERSION.txt is deliberately the only non-alice file a self-upgrade may create.
            (payload / "VERSION.txt").write_bytes((target_version + "\n").encode("utf-8"))
            manifest = build_manifest(payload, target_version, base_version)
            manifest["minimum_version"] = base_version
            manifest["self_generated"] = True
            manifest["generation"] = "governed-self-engineering"
            if provenance is not None:
                manifest["provenance"] = provenance
            (payload / "upgrade_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            updates = self.root / "alice_workspace" / "updates"
            updates.mkdir(parents=True, exist_ok=True)
            safe = target_version.replace(" ", "_").replace("/", "_")
            final = updates / f"{safe}_SELF_ENGINEERED.zip"
            partial = final.with_name(final.name + ".part")
            temp_zip = Path(tempfile.mkstemp(prefix="alice_self_pkg_", suffix=".zip")[1])
            try:
                with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
                    for f in sorted(payload.rglob("*")):
                        if f.is_file():
                            z.write(f, f.relative_to(payload).as_posix())
                # Validate the exact ZIP before exposing it to the external helper.
                from ..deployment.updater import InPlaceUpdater
                InPlaceUpdater(self.root).validate_package(temp_zip)
                shutil.copy2(temp_zip, partial)
                partial.replace(final)
            finally:
                try: temp_zip.unlink()
                except OSError: pass
            digest = self._hash_file(final)
            return {"package": str(final), "version": target_version, "sha256": digest,
                    "changed": list(changed), "manifest": manifest}
        finally:
            shutil.rmtree(payload, ignore_errors=True)

    @staticmethod
    def _validate_devour_entry_points(raw, capabilities, changes):
        """Bind each DEVOUR capability to a changed ALICE module-level callable.

        This is static validation only: candidate modules are parsed, never imported.
        The runtime promotion gate later requires the exact callable to be registered
        as the corresponding live tool and to match the installed package artifact.
        """
        if not isinstance(raw, dict):
            raise ValueError("DEVOUR candidate must declare runtime_entry_points for every selected capability")
        normalized = {}
        for key, value in raw.items():
            name = str(key).strip().lower().replace(" ", "_")
            if not name or name in normalized:
                raise ValueError("DEVOUR candidate contains duplicate or invalid runtime entry-point capability names")
            normalized[name] = value
        expected = set(capabilities)
        if set(normalized) != expected:
            raise ValueError("DEVOUR runtime_entry_points must name every and only selected capability")

        changed_sources = {
            str(item.get("path", "")).replace("\\", "/"): item.get("content", "")
            for item in changes if isinstance(item, dict)
        }
        result = {}
        for capability in sorted(expected):
            entry = normalize_entry_point(normalized[capability])
            if entry is None:
                raise ValueError(f"Invalid ALICE runtime entry point for DEVOUR capability: {capability}")
            module, qualname = entry.split(":", 1)
            if "." in qualname or keyword.iskeyword(qualname):
                raise ValueError("DEVOUR runtime entry points must name a module-level function")
            rel = module.replace(".", "/") + ".py"
            source = changed_sources.get(rel)
            if not isinstance(source, str):
                raise ValueError(f"DEVOUR runtime entry point source must be included in the candidate package: {rel}")
            try:
                tree = ast.parse(source, filename=rel)
            except SyntaxError as exc:
                raise ValueError(f"DEVOUR runtime entry point source is not valid Python: {rel}") from exc
            if not any(isinstance(node, ast.FunctionDef) and node.name == qualname
                       for node in tree.body):
                raise ValueError(f"DEVOUR runtime entry point must name a changed synchronous module-level function: {entry}")
            result[capability] = entry
        return result

    def _devour_report_provenance(self, report_obj):
        """Validate the quarantine receipt and make a compact package provenance record."""
        if not isinstance(report_obj, dict) or report_obj.get("status") not in {"digested", "analyzed"}:
            raise ValueError("DEVOUR upgrade requires a completed quarantine analysis report")
        tree_digest = str(report_obj.get("tree_sha256", "")).lower()
        if len(tree_digest) != 64 or any(char not in "0123456789abcdef" for char in tree_digest):
            raise ValueError("DEVOUR report is missing a valid source tree SHA-256")
        raw_source_path = report_obj.get("acquired_source")
        if not isinstance(raw_source_path, str) or not raw_source_path.strip():
            raise ValueError("DEVOUR report is missing the quarantined source path")
        source_path = Path(raw_source_path).expanduser()
        quarantine_root = (self.root / "alice_workspace" / "gluttony").resolve()
        try:
            resolved_source = source_path.resolve(strict=True)
            relative_source = resolved_source.relative_to(quarantine_root)
        except (OSError, ValueError) as exc:
            raise ValueError("DEVOUR source must remain inside ALICE's quarantine") from exc
        if not relative_source.parts or not resolved_source.is_dir():
            raise ValueError("DEVOUR quarantined source is not a directory")
        cursor = Path(os.path.abspath(source_path))
        while cursor != quarantine_root and quarantine_root in cursor.parents:
            if cursor.is_symlink():
                raise ValueError("DEVOUR quarantined source contains a symbolic-link path")
            cursor = cursor.parent
        for entry in resolved_source.rglob("*"):
            if entry.is_symlink():
                raise ValueError("DEVOUR quarantined source changed to contain a symbolic link")
        guard = IngestGuard()
        if guard.digest_tree(resolved_source) != tree_digest:
            raise ValueError("DEVOUR quarantined source no longer matches its recorded SHA-256")
        rescanned_security = guard.scan_tree(resolved_source)
        reported_security = report_obj.get("security")
        if not isinstance(reported_security, dict):
            raise ValueError("DEVOUR report is missing security scan results")
        try:
            reported_threats = int(reported_security.get("threat_count", -1))
            reported_files_scanned = int(reported_security.get("files_scanned", -1))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("DEVOUR report has invalid security scan counts") from exc
        if (reported_threats != rescanned_security["threat_count"]
                or reported_files_scanned != rescanned_security["files_scanned"]):
            raise ValueError("DEVOUR security findings no longer match the quarantined source")
        policy = report_obj.get("policy")
        if (not isinstance(policy, dict) or policy.get("executed_external_code") is not False
                or policy.get("activated_external_code") is not False
                or policy.get("native_reimplementation_required") is not True):
            raise ValueError("DEVOUR report does not prove that external code stayed inactive")
        candidates = report_obj.get("capability_candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("DEVOUR report contains no capability candidates to reimplement")
        candidate_names = sorted({
            str(row.get("name", "")).strip().lower()
            for row in candidates if isinstance(row, dict) and str(row.get("name", "")).strip()
        })
        if not candidate_names:
            raise ValueError("DEVOUR capability candidate names are invalid")
        license_info = report_obj.get("license")
        security = report_obj.get("security")
        acquisition = report_obj.get("acquisition")
        if not isinstance(license_info, dict) or not isinstance(security, dict):
            raise ValueError("DEVOUR report is missing license or security analysis")
        try:
            canonical_report = json.dumps(
                report_obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("DEVOUR analysis report is not valid JSON data") from exc
        if len(canonical_report) > SelfManager.MAX_DEVOUR_REPORT_BYTES:
            raise ValueError("DEVOUR analysis report exceeds the provenance size limit")
        report_fingerprint = hashlib.sha256(canonical_report).hexdigest()
        source = str(report_obj.get("source", ""))
        license_kind = str(license_info.get("kind", "Unknown"))[:120]
        license_review_required = (
            not license_kind or license_kind.casefold().startswith("no license")
            or "manual review" in license_kind.casefold()
            or license_kind.upper() in {"GPL", "AGPL", "LGPL", "MPL"}
        )
        threat_count = max(0, reported_threats)
        files_scanned = max(0, reported_files_scanned)
        return {
            "source_label": str(report_obj.get("source_label", ""))[:160],
            "source_fingerprint_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "report_sha256": report_fingerprint,
            "tree_sha256": tree_digest,
            "acquisition_method": str((acquisition or {}).get("method", "unknown"))[:80]
                if isinstance(acquisition, dict) else "unknown",
            "license": {"kind": license_kind,
                        "files": [str(x)[:200] for x in license_info.get("files", [])[:20]]
                        if isinstance(license_info.get("files", []), list) else [],
                        "review_required": license_review_required},
            "security": {"threat_count": threat_count, "files_scanned": files_scanned,
                         "review_required": threat_count > 0},
            "candidate_capabilities": candidate_names,
            "external_code_executed": False,
            "external_code_activated": False,
        }

    def prepare_devour_upgrade(self, goal, report, repair_attempts=3, approved_capabilities=None):
        """Digest an external project report into an ALICE-native, verified upgrade package.

        External source remains quarantined and is supplied to the engineering model only as
        evidence. The model is explicitly forbidden from copying executable external files;
        it must reimplement selected capabilities inside ALICE's governed source boundary.
        """
        if not self.router:
            raise RuntimeError("Upgrade engine not configured")
        base_version=read_version(self.root)
        if not isinstance(report,(str,Path)):
            raise ValueError("DEVOUR native reimplementation requires a persisted report with individual approvals")
        from ..gluttony.review import DevourReviewStore
        report_path=Path(report).expanduser().resolve(strict=True)
        approval_evidence=DevourReviewStore(self.root).approval_evidence(report_path,approved_capabilities)
        report_bytes=report_path.read_bytes()
        if hashlib.sha256(report_bytes).hexdigest()!=approval_evidence.get("report_sha256"):
            raise ValueError("DEVOUR report changed after capability approval")
        report_obj=json.loads(report_bytes.decode("utf-8"))
        if report_obj.get("job_type")=="multi_source_devour":
            # DevourReviewStore has rehashed every child quarantine and rebuilt the
            # aggregate comparisons before returning approval evidence.
            provenance=approval_evidence.get("provenance")
            if not isinstance(provenance,dict) or provenance.get("external_code_executed") is not False:
                raise ValueError("Multi-source DEVOUR provenance is missing or unverified")
        else:
            provenance=self._devour_report_provenance(report_obj)
        approval_rows=approval_evidence.get("approvals",[])
        approved_names=sorted({str(row.get("capability","")).strip().lower() for row in approval_rows})
        if not approved_names:
            raise ValueError("DEVOUR native reimplementation requires at least one individually approved capability")
        decisions=approval_evidence.get("decisions",{})
        if any(decisions.get(name) not in {"integrate_behind_alice_interface","implement_native_equivalent"}
               for name in approved_names):
            raise ValueError("A reuse-existing-component decision does not require or permit a new candidate package")
        approved_set=set(approved_names)
        native_evidence=approval_evidence.get("native_evidence",{})
        candidates=[row for row in native_evidence.get("candidates",[])
                    if isinstance(row,dict) and str(row.get("name","")).strip().lower() in approved_set]
        plan=[row for row in native_evidence.get("plan",[])
              if isinstance(row,dict) and str(row.get("capability","")).strip().lower() in approved_set]
        candidate_files={str(path) for row in candidates for path in row.get("evidence_files",[]) if isinstance(path,str)}
        evidence={"source":native_evidence.get("source",report_obj.get("source")),
                  "license":native_evidence.get("license",report_obj.get("license")),
                  "security":native_evidence.get("security",report_obj.get("security")),
                  "architecture":native_evidence.get("architecture",report_obj.get("architecture")),
                  "candidates":candidates,"plan":plan,
                  "samples":[row for row in native_evidence.get("samples",report_obj.get("source_samples",[]))
                             if isinstance(row,dict) and row.get("path") in candidate_files] }
        evidence["approved_capability_names"]=approved_names
        evidence["approved_decisions"]={name:decisions[name] for name in approved_names}
        inventory=[self._relative(p) for p in (self.root/"alice").rglob("*.py") if not self._is_protected(self._relative(p))]
        select_prompt=(
            "You are Alice's senior capability architect. An external project has been safely quarantined and statically analyzed. "
            "Select the smallest set of ALICE source files plus any NEW alice/ files needed for the approved per-capability decisions. "
            "For integrate_behind_alice_interface, preserve ALICE-owned interfaces and implement a native adapter/integration. "
            "For implement_native_equivalent, implement ALICE-owned behavior without external code. "
            "Always include at least one focused alice/tests/test_*.py regression test for the selected capability. "
            "Do not copy external project files, imports, credentials, persistence, malware, evasion, or license-incompatible code. "
            "External code must never execute. Protected security/permission/device-consent areas are forbidden. Return ONLY JSON "
            '{"reason":"...","files":["alice/path.py"],"capabilities":["..."]}.\nGOAL:\n'+str(goal)+
            "\nCURRENT VERSION:\n"+base_version+"\nALICE SOURCE INVENTORY:\n"+json.dumps(inventory)+
            "\nDEVOUR EVIDENCE:\n"+json.dumps(evidence,ensure_ascii=False)[:900000])
        selected=self._parse(self._engineering_ask(select_prompt)); paths=selected.get("files",[])
        if not isinstance(paths,list) or not paths or len(paths)>self.MAX_FILES: raise ValueError("Invalid devour file selection")
        selected_capabilities=selected.get("capabilities",[])
        normalized_selected=([str(name).strip().lower() for name in selected_capabilities]
                             if isinstance(selected_capabilities,list) else [])
        if (not normalized_selected or len(set(normalized_selected))!=len(normalized_selected)
                or any(name not in approved_set for name in normalized_selected)):
            raise ValueError("Engineer must select only individually approved DEVOUR capabilities")
        selected_items=[]
        for raw in paths:
            rel=Path(str(raw).replace("\\","/")); rel_text=rel.as_posix()
            if rel.is_absolute() or ".." in rel.parts or not rel_text.startswith("alice/") or self._is_protected(rel_text):
                raise ValueError(f"Invalid or protected devour selection: {rel_text}")
            p=self.root/rel
            if p.is_symlink() or (p.exists() and not p.is_file()):
                raise ValueError(f"Devour selection must be a regular ALICE source file: {rel_text}")
            selected_items.append({"path":rel_text,"content":p.read_text(encoding="utf-8") if p.is_file() else ""})
        selected_test_paths = sorted(
            item["path"] for item in selected_items
            if item["path"].startswith("alice/tests/")
            and Path(item["path"]).name.startswith("test_")
            and Path(item["path"]).suffix == ".py"
        )
        if not selected_test_paths:
            raise ValueError("DEVOUR selection must include a focused alice/tests/test_*.py regression test")
        last_error=""
        for attempt in range(repair_attempts+1):
            prompt=(
                "You are Alice's senior software engineer. Implement only the explicit per-capability decision recorded in DEVOUR evidence. "
                "For integrate_behind_alice_interface, use ALICE-owned interfaces and native adapter code. For implement_native_equivalent, write native ALICE behavior. "
                "Never import or execute the external project. Do not copy its files verbatim. Preserve ALICE architecture, existing capabilities, security, permissions, voice, memory and updater behavior. "
                "Return ONLY JSON: {\"reason\":\"...\",\"runtime_entry_points\":{\"capability_name\":\"alice.module:function\"},\"changes\":[{\"path\":\"alice/...\",\"content\":\"complete file content\"}]}. "
                "Changes must include or update a focused selected test under alice/tests/test_*.py that proves the selected capability behavior. "
                "For every selected capability, declare one synchronous module-level ALICE function in a changed non-test alice/ module. "
                "Wire that exact function into ALICE's ToolRegistry under the same capability name; never claim a helper or unregistered function. "
                "runtime_entry_points must contain every and only the selected capability names, with values in alice.module:function form. "
                "The focused test and Alice's full test suite must both pass. Changes must be complete files, bounded and syntactically valid.\nGOAL:\n"+str(goal)+
                "\nATTEMPT:\n"+str(attempt+1)+"\nPREVIOUS FAILURE:\n"+last_error+
                "\nSELECTED FILES:\n"+json.dumps(selected_items)+"\nDEVOUR EVIDENCE:\n"+json.dumps(evidence,ensure_ascii=False)[:900000])
            obj=self._parse(self._engineering_ask(prompt)); items=obj.get("changes",[]); self._validate_items(items)
            allowed_paths={str(item["path"]).replace("\\", "/") for item in selected_items}
            changed_paths={str(item["path"]).replace("\\", "/") for item in items}
            out_of_scope=sorted(changed_paths-allowed_paths)
            if out_of_scope:
                last_error="candidate changed files outside the selected native implementation scope: "+", ".join(out_of_scope)
                continue
            candidate_tests = sorted(
                str(item["path"]).replace("\\", "/") for item in items
                if str(item["path"]).replace("\\", "/").startswith("alice/tests/")
                and Path(str(item["path"]).replace("\\", "/")).name.startswith("test_")
                and Path(str(item["path"]).replace("\\", "/")).suffix == ".py"
            )
            if not candidate_tests:
                last_error="DEVOUR candidate must add or update a selected alice/tests/test_*.py regression test"
                continue
            if not set(candidate_tests).issubset(selected_test_paths):
                last_error="DEVOUR candidate test file was not included in the architect's selected scope"
                continue
            for item in items:
                rel = str(item["path"]).replace("\\", "/")
                if rel in candidate_tests:
                    names = {
                        node.name for node in ast.walk(ast.parse(item["content"], filename=rel))
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    }
                    if not any(name.startswith("test_") for name in names):
                        last_error=f"DEVOUR candidate test file defines no pytest test function: {rel}"
                        break
            else:
                last_error=""
            if last_error:
                continue
            try:
                runtime_entry_points = self._validate_devour_entry_points(
                    obj.get("runtime_entry_points"), normalized_selected, items)
            except ValueError as exc:
                last_error = str(exc)
                continue
            stage=self._copy_tree_for_stage()
            try:
                self._apply_items(stage,items); test=self._stage_test_with_candidate_tests(stage,candidate_tests)
                if test.returncode:
                    last_error=(test.stderr or test.stdout)[-20000:]
                    continue
                passed_test_paths = getattr(test, "candidate_test_paths", [])
                if passed_test_paths != candidate_tests:
                    last_error="candidate-specific regression test did not produce isolated passing evidence"
                    continue
                before=self._safety_invariants(); after={}
                for rel,digest in before.items():
                    q=stage/rel
                    if not q.exists() or self._hash_file(q)!=digest: raise ValueError("Protected invariant changed: "+rel)
                sandbox = getattr(test, "sandbox_evidence", None)
                focused_sandbox = getattr(test, "candidate_test_sandbox_evidence", None)
                isolated = (isinstance(sandbox, dict) and sandbox.get("verified") is True
                            and isinstance(focused_sandbox, dict)
                            and focused_sandbox.get("verified") is True)
                provenance_record={
                    "kind":"devour_native_reimplementation",
                    "devour":provenance,
                    "selected_capabilities":sorted(normalized_selected),
                    "declared_entry_points":runtime_entry_points,
                    "user_approval":{"per_capability":True,
                        "report_sha256":approval_evidence["report_sha256"],
                        "tree_sha256":approval_evidence["tree_sha256"],
                        "decisions":decisions,
                        "approvals":[{key:row.get(key) for key in
                             ("capability","decision","candidate_sha256","approved_at","reviewer","approval_method")}
                            for row in approval_rows]},
                    "verification":{"compile":"passed","test_suite":"passed",
                                     "summary":str(test.stdout or "").strip()[-2000:],
                                     "candidate_tests":{"paths":candidate_tests,
                                         "summary":getattr(test,"candidate_test_summary",""),
                                         "sandbox":focused_sandbox if isinstance(focused_sandbox,dict)
                                             and focused_sandbox.get("verified") is True else {"verified":False}},
                                     "execution_isolation":("Docker Linux container: non-root, no network, read-only root and candidate mount, dropped capabilities, no-new-privileges, bounded CPU/memory/PIDs"
                                         if isolated else "sandbox evidence unavailable; candidate must remain blocked"),
                                     "sandbox":sandbox if isolated else {"verified":False}},
                    "promotion":{"promoted":False,"eligible":False,
                                 "blocked_until_os_sandbox":not isolated,
                                 "requires_explicit_install":True},
                    "rollback":{"strategy":"InPlaceUpdater backup plus post-update test rollback",
                                 "required_before_activation":True},
                }
                package=self._package_candidate(stage,[x["path"] for x in items],base_version,
                                                provenance=provenance_record)
                capability_evidence=[]
                if self.capability_manager is not None:
                    approvals_by_name={str(row.get("capability", "")).strip().lower():row
                                       for row in approval_rows}
                    candidate_status=("tested_candidate_isolated_pending_review" if isolated
                                      else "tested_candidate_pending_isolation")
                    verification=provenance_record["verification"]
                    for capability in sorted(normalized_selected):
                        approval=approvals_by_name.get(capability)
                        if not approval:
                            raise ValueError("DEVOUR capability registry receipt lacks matching approval evidence")
                        capability_evidence.append(self.capability_manager.record_devour_candidate(
                            capability,
                            candidate_version=package["version"],
                            candidate_sha256=package["sha256"],
                            report_sha256=approval_evidence["report_sha256"],
                            tree_sha256=approval_evidence["tree_sha256"],
                            capability_candidate_sha256=approval.get("candidate_sha256"),
                            candidate_status=candidate_status,
                            test_paths=candidate_tests,
                            test_summary=getattr(test,"candidate_test_summary",""),
                            sandbox=verification.get("sandbox",{}),
                            approval_method=approval.get("approval_method",""),
                            approval_decision=approval.get("decision","implement_native_equivalent"),
                            entry_point=runtime_entry_points[capability],
                        ))
                self._write_evolution_journal({"timestamp":time.time(),"type":"devour_native_reimplementation","base_version":base_version,"target_version":package["version"],"goal":goal,"source":report_obj.get("source"),"changed":package["changed"],"sha256":package["sha256"],"attempt":attempt+1})
                return {"ok":True,"status":("tested_candidate_isolated_pending_review" if isolated else "tested_candidate_pending_isolation"),"promotion_eligible":False,
                        "package":package,"capabilities":sorted(normalized_selected),"attempt":attempt+1,
                        "capability_evidence":capability_evidence}
            finally: shutil.rmtree(stage,ignore_errors=True)
        raise RuntimeError("Devour reimplementation could not produce a passing candidate after bounded repair attempts: "+last_error[-4000:])

    def _engineering_ask(self, prompt):
        """Use the local-first engineering brain when the router supports it.

        The fallback keeps older test doubles and compatible routers working.
        """
        fn=getattr(self.router, "engineering_ask", None)
        return fn(prompt) if callable(fn) else self.router.ask(prompt)

    def _compile_tree(self, cwd):
        env=os.environ.copy(); env["PYTHONDONTWRITEBYTECODE"]="1"
        return subprocess.run([os.sys.executable, "-m", "compileall", "-q", "alice"], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)

    def prepare_self_upgrade(self, goal, repair_attempts=2):
        """Engineer, test and package an upgrade without modifying the live process.

        This is the true self-upgrade path: the running Alice instance only creates a
        verified package. The external update helper performs the actual replacement
        after Alice exits. A bounded repair loop lets the engineer fix candidate test
        failures before the package is ever scheduled.
        """
        if not self.router:
            raise RuntimeError("Upgrade engine not configured")
        base_version = read_version(self.root)
        before = self.diagnostics()
        inventory = [self._relative(p) for p in (self.root / "alice").rglob("*.py")
                     if not self._is_protected(self._relative(p))]
        selection_prompt = (
            "You are Alice's senior software architect. Identify the SMALLEST set of "
            "existing alice/*.py files that must change to achieve the requested upgrade. "
            "You may request NEW files only under alice/. Never select protected security, "
            "permission, device-consent, credentials, or files outside alice/. Return ONLY JSON: "
            '{"reason":"...","files":["alice/path.py"]}.\nGOAL:\n' + str(goal) +
            "\nCURRENT VERSION:\n" + base_version + "\nCURRENT DIAGNOSTICS:\n" + json.dumps(before) +
            "\nSOURCE INVENTORY:\n" + json.dumps(inventory)
        )
        selected = self._parse(self._engineering_ask(selection_prompt))
        paths = selected.get("files", [])
        if not isinstance(paths, list) or not paths or len(paths) > self.MAX_FILES:
            raise ValueError("Upgrade engineer selected an invalid file set")
        selected_items=[]
        for raw in paths:
            rel=Path(str(raw).replace("\\","/")); rel_text=rel.as_posix()
            if rel.is_absolute() or ".." in rel.parts or not rel_text.startswith("alice/") or self._is_protected(rel_text):
                raise ValueError(f"Invalid or protected upgrade selection: {rel_text}")
            p=self.root/rel
            selected_items.append({"path":rel_text,"content":p.read_text(encoding="utf-8") if p.is_file() else None})

        last_error=""
        for attempt in range(repair_attempts + 1):
            implementation_prompt = (
                "You are Alice's senior software engineer. Implement the requested upgrade using ONLY "
                "the selected files. Return ONLY JSON: {\"reason\":\"...\",\"changes\":[{\"path\":\"alice/...py\",\"content\":\"complete file content\"}]}. "
                "Make the smallest safe change. Never weaken security/approval controls, access credentials, "
                "add persistence/evasion/malware, or modify files outside the selected set. The result must pass "
                "Alice's complete test suite. If a previous candidate failed, repair it using the failure report.\n"
                "GOAL:\n" + str(goal) + "\nATTEMPT:\n" + str(attempt+1) +
                "\nPREVIOUS FAILURE:\n" + last_error + "\nSELECTED FILES:\n" + json.dumps(selected_items)
            )
            obj=self._parse(self._engineering_ask(implementation_prompt))
            items=obj.get("changes",[])
            self._validate_items(items)
            impact=self.engineering_gate.preflight(self.root, items)
            stage=self._copy_tree_for_stage()
            try:
                self._apply_items(stage, items)
                test=self._stage_test(stage)
                if test.returncode:
                    last_error=(test.stderr or test.stdout or "candidate tests failed")[-12000:]
                    selected_items=[{"path":i["path"],"content":(stage/i["path"]).read_text(encoding="utf-8")} for i in items]
                    continue
                before_inv=self._safety_invariants()
                for rel,digest in before_inv.items():
                    candidate=stage/rel
                    if not candidate.exists() or self._hash_file(candidate)!=digest:
                        raise ValueError(f"protected invariant changed: {rel}")
                package=self._package_candidate(stage,[i["path"] for i in items],base_version)
                self._write_evolution_journal({"time":time.time(),"base_version":base_version,
                    "target_version":package["version"],"goal":str(goal),"changed":package["changed"],
                    "tests":"passed","attempt":attempt+1,"sha256":package["sha256"]})
                return {"ok":True,"status":"package_ready","promoted":False,"base_version":base_version,
                        "target_version":package["version"],"package":package["package"],"sha256":package["sha256"],
                        "changed":package["changed"],"impact":impact,"tests":test.stdout.strip(),
                        "reason":"candidate_verified_and_packaged","reason_from_engineer":obj.get("reason",selected.get("reason",""))}
            finally:
                shutil.rmtree(stage,ignore_errors=True)
        self._write_evolution_journal({"time":time.time(),"base_version":base_version,"goal":str(goal),
            "status":"failed","reason":"candidate_tests_failed","last_error":last_error[-4000:]})
        return {"ok":False,"status":"candidate_failed","promoted":False,"base_version":base_version,
                "reason":"candidate_tests_failed_after_repair_attempts","output":last_error}

    def self_upgrade(self, goal):
        """Have Alice identify, implement, test and safely promote a minimal upgrade."""
        if not self.router:
            raise RuntimeError("Upgrade engine not configured")
        before = self.diagnostics()
        inventory = []
        for p in (self.root / "alice").rglob("*.py"):
            rel = self._relative(p)
            if not self._is_protected(rel):
                inventory.append(rel)

        # Stage 1: ask only which files are actually relevant. This prevents a
        # model from hallucinating complete replacements for unrelated source.
        selection_prompt = (
            "You are Alice's senior software architect. Identify the SMALLEST set of "
            "existing alice/*.py files that must change to achieve the requested upgrade. "
            "You may also request one NEW file under alice/ if genuinely necessary. "
            "Never select protected security/permission/device-consent files, credentials, "
            "or files outside alice/. Return ONLY JSON: "
            '{"reason":"...","files":["alice/path.py"]}. '
            "Do not propose code yet.\nGOAL:\n" + str(goal) +
            "\nCURRENT DIAGNOSTICS:\n" + json.dumps(before) +
            "\nSOURCE INVENTORY:\n" + json.dumps(inventory)
        )
        selected = self._parse(self._engineering_ask(selection_prompt))
        paths = selected.get("files", [])
        if not isinstance(paths, list) or not paths or len(paths) > self.MAX_FILES:
            raise ValueError("Upgrade engineer selected an invalid file set")
        selected_items = []
        for raw in paths:
            rel = Path(str(raw).replace("\\", "/"))
            rel_text = rel.as_posix()
            if rel.is_absolute() or ".." in rel.parts or not rel_text.startswith("alice/"):
                raise ValueError("Upgrade selection outside alice/")
            if self._is_protected(rel_text):
                raise ValueError(f"Upgrade selection contains protected path: {rel_text}")
            p = self.root / rel
            if p.exists() and p.is_file():
                selected_items.append({"path": rel_text, "content": p.read_text(encoding="utf-8")})
            elif not p.exists():
                # New files are allowed, but only under alice/.
                selected_items.append({"path": rel_text, "content": None})
            else:
                raise ValueError(f"Upgrade target is not a file: {rel_text}")

        implementation_prompt = (
            "You are Alice's senior software engineer. Implement the requested upgrade "
            "using ONLY the selected files below. Return ONLY JSON: "
            '{"reason":"...","changes":[{"path":"alice/...py","content":"complete file content"}]}. '
            "Make the smallest safe change. You may add a selected new file. Never delete files, "
            "weaken safety/approval controls, access credentials, add persistence/evasion/malware, "
            "or modify files outside the selected set. Preserve existing public APIs unless a "
            "compatible extension is required. The result must pass Alice's complete test suite.\n"
            "GOAL:\n" + str(goal) +
            "\nSELECTED FILES:\n" + json.dumps(selected_items)
        )
        raw = self._engineering_ask(implementation_prompt)
        obj = self._parse(raw)
        result = self.apply_patch(obj.get("changes", []))
        result["reason_from_engineer"] = str(obj.get("reason", selected.get("reason", "")))
        return result

    @staticmethod
    def _parse(raw):
        text = str(raw).strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])
        a, b = text.find("{"), text.rfind("}")
        if a < 0 or b < a:
            raise ValueError("No JSON upgrade plan")
        return json.loads(text[a:b+1])

    def self_repair(self, issue):
        return self.self_upgrade(
            "Repair this issue with the smallest safe source change: " + str(issue)
        )

    def update_from_git(self):
        if not (self.root / ".git").exists():
            raise RuntimeError("Alice is not a git checkout")
        backup = self.snapshot()
        r = subprocess.run(
            ["git", "pull", "--ff-only"], cwd=self.root,
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode:
            return {"ok": False, "backup": backup, "output": r.stderr or r.stdout}
        test = self.run_tests()
        if test.returncode:
            self.restore(backup)
            return {"ok": False, "rolled_back": True, "backup": backup,
                    "output": test.stderr or test.stdout}
        return {"ok": True, "backup": backup, "output": r.stdout}
