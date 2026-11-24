"""Persistent self-model and capability graph for ALICE.

The capability registry answers a different question from simple feature discovery:
what can ALICE do *right now*, how reliable is it, what does it depend on, what
permissions does it need, what recently failed, and what verified alternative can
be used?  The implementation is deliberately backward compatible with older
capabilities.json records.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable
from ..execution.callable_provenance import callable_provenance, normalize_entry_point


STATUS_AVAILABLE = "available"
STATUS_DEGRADED = "degraded"
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNVERIFIED = "unverified"


@dataclass
class Capability:
    name: str
    description: str
    kind: str = "builtin"
    source: str = "alice"
    enabled: bool = True
    learned_at: float = 0.0
    status: str = STATUS_UNVERIFIED
    reliability: float = 0.0
    version: str = ""
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    configured: bool = True
    verified: bool = False
    last_success: float | None = None
    last_failure: float | None = None
    failure_count: int = 0
    success_count: int = 0
    last_error: str = ""
    verification_note: str = ""
    acquisition_evidence: list[dict] = field(default_factory=list)


class CapabilityGap(RuntimeError):
    pass


class CapabilityManager:
    def __init__(self, root=None, *, initialize=True):
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.path = self.root / "alice_workspace" / "capabilities.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # Live callable references are intentionally process-local. Persisted hashes
        # alone must never authorize a DEVOUR capability after restart.
        self._runtime_callables: dict[str, dict] = {}
        self.capabilities: dict[str, Capability] = {}
        self._load()
        if initialize:
            self._seed()
            self._save()

    @staticmethod
    def _normalise_record(value: dict) -> Capability:
        """Load old registry records without losing forward-compatible fields."""
        fields = {f.name for f in Capability.__dataclass_fields__.values()}
        clean = {k: v for k, v in value.items() if k in fields}
        for key in ("permissions", "dependencies", "alternatives"):
            raw = clean.get(key, [])
            clean[key] = [str(x) for x in raw] if isinstance(raw, (list, tuple, set)) else []
        clean.setdefault("status", STATUS_UNVERIFIED)
        clean.setdefault("reliability", 0.0)
        clean.setdefault("version", "")
        clean.setdefault("configured", bool(clean.get("enabled", True)))
        clean.setdefault("verified", False)
        clean.setdefault("last_success", None)
        clean.setdefault("last_failure", None)
        clean.setdefault("failure_count", 0)
        clean.setdefault("success_count", 0)
        clean.setdefault("last_error", "")
        clean.setdefault("verification_note", "")
        evidence = clean.get("acquisition_evidence", [])
        clean["acquisition_evidence"] = [dict(row) for row in evidence if isinstance(row, dict)][-50:] if isinstance(evidence, list) else []
        return Capability(**clean)

    def _load(self):
        if not self.path.exists():
            return
        # A corrupt capability registry may contain the only durable candidate,
        # approval, and runtime-verification receipts. Never reinterpret it as an
        # empty registry and then overwrite the evidence with seeded defaults.
        try:
            size = self.path.stat().st_size
            if size > 8 * 1024 * 1024:
                raise CapabilityGap("Capability registry exceeds the 8 MiB safety limit; original preserved")
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict) or any(not isinstance(value, dict) for value in data.values()):
                raise CapabilityGap("Capability registry root/records are malformed; original preserved")
            loaded = {}
            for key, value in data.items():
                name = str(key)
                if not name or len(name) > 128:
                    raise CapabilityGap("Capability registry contains an invalid capability key; original preserved")
                loaded[name] = self._normalise_record(value)
            self.capabilities = loaded
        except CapabilityGap:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, AttributeError) as exc:
            raise CapabilityGap(
                f"Capability registry could not be safely loaded; original preserved ({type(exc).__name__})"
            ) from exc

    def _seed(self):
        seeds = {
            "computer_control": "Operate the Windows desktop with keyboard, mouse and screenshots.",
            "browser_automation": "Navigate and interact with websites using a controlled browser.",
            "web_research": "Search public web information and fetch pages as untrusted data.",
            "software_building": "Create, run, test, repair and verify multi-file software projects.",
            "self_diagnostics": "Diagnose Alice source code and validate repairs before keeping them.",
            "voice_io": "Accept voice input and speak responses.",
            "multi_model_reasoning": "Use specialist AI providers when a capability gap or hard review requires them.",
            "persistent_memory": "Store useful task outcomes and learned capability metadata locally.",
        }
        for name, desc in seeds.items():
            if name not in self.capabilities:
                self.capabilities[name] = Capability(
                    name=name,
                    description=desc,
                    learned_at=time.time(),
                    status=STATUS_UNVERIFIED,
                    configured=True,
                    verified=False,
                )

    def _save(self):
        with self._lock:
            payload = json.dumps({k: asdict(v) for k, v in self.capabilities.items()}, indent=2)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=self.path.parent,
                    prefix=self.path.name + ".", suffix=".tmp", delete=False,
                ) as output:
                    temporary = Path(output.name)
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()

    @staticmethod
    def _clean_names(values: Iterable[str] | None) -> list[str]:
        return sorted({str(x).strip().lower().replace(" ", "_") for x in (values or []) if str(x).strip()})

    def bind_runtime_callable(self, name, function) -> bool:
        """Bind the exact live ALICE-owned callable installed in the tool registry."""
        key = str(name).strip().lower().replace(" ", "_")
        identity = callable_provenance(function, self.root)
        with self._lock:
            if not key or identity is None:
                self._runtime_callables.pop(key, None)
                return False
            self._runtime_callables[key] = {"function": function, "identity": identity}
        return True

    def _bound_runtime_identity(self, name, function):
        binding = self._runtime_callables.get(str(name).strip().lower().replace(" ", "_"))
        if not isinstance(binding, dict) or binding.get("function") is not function:
            return None
        current = callable_provenance(function, self.root)
        if current is None or current != binding.get("identity"):
            return None
        return current

    def register(
        self,
        name,
        description,
        kind="learned",
        source="alice",
        *,
        version="",
        permissions=None,
        dependencies=None,
        alternatives=None,
        configured=True,
    ):
        name = str(name).strip().lower().replace(" ", "_")
        if not name or len(name) > 80:
            raise ValueError("Invalid capability name")
        with self._lock:
            now = time.time()
            previous = self.capabilities.get(name)
            preserved_version = str(version or "")
            if not preserved_version and previous:
                for receipt in reversed(previous.acquisition_evidence):
                    installed = receipt.get("installation") if isinstance(receipt,dict) else None
                    if isinstance(installed,dict) and installed.get("status") in {
                        "installed_pending_runtime_verification", "runtime_verified"
                    }:
                        preserved_version = str(installed.get("version", ""))
                        if preserved_version:
                            break
            capability = Capability(
                name,
                str(description)[:1000],
                kind,
                source,
                True,
                now,
                STATUS_UNVERIFIED,
                0.0,
                preserved_version,
                self._clean_names(permissions),
                self._clean_names(dependencies),
                self._clean_names(alternatives),
                bool(configured),
                False,
                None,
                None,
                0,
                0,
                "",
                "Registered; runtime verification is still required.",
                list(previous.acquisition_evidence) if previous else [],
            )
            self.capabilities[name] = capability
            self._save()
            return asdict(capability)

    @staticmethod
    def _sha256(value, label):
        digest = str(value or "").lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"DEVOUR candidate evidence requires a valid {label} SHA-256")
        return digest

    def record_devour_candidate(
        self, name, *, candidate_version, candidate_sha256, report_sha256,
        tree_sha256, capability_candidate_sha256, candidate_status,
        test_paths, test_summary, sandbox, approval_method, approval_decision="implement_native_equivalent",
        entry_point=None,
    ):
        """Persist candidate provenance without claiming the capability is active."""
        name = str(name).strip().lower().replace(" ", "_")
        if not name or len(name) > 80:
            raise ValueError("Invalid DEVOUR capability name")
        allowed = {"tested_candidate_pending_isolation", "tested_candidate_isolated_pending_review"}
        if candidate_status not in allowed:
            raise ValueError("Unsupported DEVOUR candidate status")
        paths = []
        for raw in test_paths if isinstance(test_paths, (list, tuple)) else []:
            rel = str(raw).replace("\\", "/")
            parts = rel.split("/")
            if (not rel.startswith("alice/tests/test_") or not rel.endswith(".py")
                    or any(part in {"", ".", ".."} for part in parts)):
                raise ValueError("DEVOUR candidate evidence must name focused ALICE tests")
            paths.append(rel)
        paths = sorted(set(paths))
        if not paths:
            raise ValueError("DEVOUR candidate evidence requires a focused test path")
        sandbox = sandbox if isinstance(sandbox, dict) else {}
        sandbox_verified = sandbox.get("verified") is True
        if candidate_status == "tested_candidate_isolated_pending_review" and not sandbox_verified:
            raise ValueError("Isolated DEVOUR candidate status requires verified sandbox evidence")
        normalized_entry_point = normalize_entry_point(entry_point) if entry_point else None
        if entry_point and normalized_entry_point is None:
            raise ValueError("DEVOUR runtime entry point must be an ALICE module:function reference")
        if candidate_status == "tested_candidate_isolated_pending_review" and normalized_entry_point is None:
            raise ValueError("Isolated DEVOUR candidate status requires a declared runtime entry point")
        checks = sandbox.get("checks", {}) if isinstance(sandbox.get("checks"), dict) else {}
        receipt = {
            "source": "devour",
            "status": candidate_status,
            "candidate_version": str(candidate_version or "")[:80],
            "candidate_sha256": self._sha256(candidate_sha256, "candidate package"),
            "report_sha256": self._sha256(report_sha256, "report"),
            "tree_sha256": self._sha256(tree_sha256, "source tree"),
            "capability_candidate_sha256": self._sha256(capability_candidate_sha256, "capability candidate"),
            "approval_method": str(approval_method or "")[:80],
            "approval_decision": str(approval_decision or "implement_native_equivalent")[:80],
            "entry_point": normalized_entry_point,
            "candidate_tests": {
                "paths": paths[:20],
                "summary": str(test_summary or "").splitlines()[-1][:180],
            },
            "sandbox": {
                "verified": sandbox_verified,
                "backend": str(sandbox.get("backend", ""))[:40],
                "image": str(sandbox.get("image", ""))[:120],
                "image_id": str(sandbox.get("image_id", ""))[:128],
                "checks": {key: bool(checks[key]) for key in (
                    "network_disabled", "only_candidate_bind_mount", "read_only_root",
                    "candidate_read_only", "non_root", "no_new_privileges",
                ) if key in checks},
            },
            "recorded_at": time.time(),
        }
        with self._lock:
            capability = self.capabilities.get(name)
            if capability is None:
                capability = Capability(
                    name=name,
                    description=f"Native DEVOUR candidate for {name}; installation and runtime verification are pending.",
                    kind="acquired_candidate",
                    source="devour_review",
                    enabled=True,
                    learned_at=time.time(),
                    status=STATUS_UNVERIFIED,
                    version="",
                    configured=False,
                    verified=False,
                    verification_note="Candidate evidence is recorded; no runtime availability has been verified.",
                )
                self.capabilities[name] = capability
            rows = capability.acquisition_evidence
            rows[:] = [row for row in rows if not (
                row.get("candidate_sha256") == receipt["candidate_sha256"]
                and row.get("capability_candidate_sha256") == receipt["capability_candidate_sha256"]
            )]
            rows.append(receipt)
            del rows[:-50]
            self._save()
            return {
                "name": name,
                "candidate_status": candidate_status,
                "recorded": True,
                "active": False,
                "verified": False,
                "candidate_sha256": receipt["candidate_sha256"],
            }

    def validate_devour_candidate_installation(
        self, name, *, candidate_version, package_sha256, report_sha256,
        tree_sha256, capability_candidate_sha256, entry_point=None,
    ):
        """Require a current isolated, per-capability receipt before package install."""
        name = str(name).strip().lower().replace(" ", "_")
        expected = {
            "candidate_sha256": self._sha256(package_sha256,"candidate package"),
            "report_sha256": self._sha256(report_sha256,"report"),
            "tree_sha256": self._sha256(tree_sha256,"source tree"),
            "capability_candidate_sha256": self._sha256(capability_candidate_sha256,"capability candidate"),
        }
        expected_entry_point = normalize_entry_point(entry_point) if entry_point else None
        if entry_point and expected_entry_point is None:
            return {"ok": False, "reason": "invalid_declared_runtime_entry_point", "name": name}
        version = str(candidate_version or "")[:80]
        capability = self.capabilities.get(name)
        receipts = capability.acquisition_evidence if capability else []
        for receipt in reversed(receipts):
            if not isinstance(receipt,dict):
                continue
            if (receipt.get("status")!="tested_candidate_isolated_pending_review"
                    or receipt.get("candidate_version")!=version
                    or any(receipt.get(key)!=value for key,value in expected.items())
                    or (expected_entry_point is not None
                        and receipt.get("entry_point") != expected_entry_point)
                    or not isinstance(receipt.get("sandbox"),dict)
                    or receipt["sandbox"].get("verified") is not True):
                continue
            return {"ok":True,"name":name,"candidate_sha256":expected["candidate_sha256"],
                    "candidate_version":version,"entry_point":receipt.get("entry_point")}
        return {"ok":False,"reason":"matching_isolated_per_capability_candidate_receipt_required",
                "name":name,"candidate_sha256":expected["candidate_sha256"]}

    def record_devour_installation(
        self, name, *, candidate_version, package_sha256, report_sha256,
        tree_sha256, capability_candidate_sha256, test_summary, rollback_backup_sha256,
        installed_artifacts=None,
    ):
        """Record successful package tests and expected installed-file identities without activating."""
        validation=self.validate_devour_candidate_installation(
            name,candidate_version=candidate_version,package_sha256=package_sha256,
            report_sha256=report_sha256,tree_sha256=tree_sha256,
            capability_candidate_sha256=capability_candidate_sha256)
        if not validation.get("ok"):
            raise CapabilityGap(validation.get("reason","DEVOUR install receipt mismatch"))
        backup_digest=self._sha256(rollback_backup_sha256,"rollback backup manifest")
        name=validation["name"]
        capability=self.capabilities[name]
        expected={"candidate_sha256":self._sha256(package_sha256,"candidate package"),
                  "report_sha256":self._sha256(report_sha256,"report"),
                  "tree_sha256":self._sha256(tree_sha256,"source tree"),
                  "capability_candidate_sha256":self._sha256(capability_candidate_sha256,"capability candidate")}
        receipt=next(row for row in reversed(capability.acquisition_evidence)
                     if isinstance(row,dict)
                     and row.get("candidate_version")==validation["candidate_version"]
                     and row.get("status")=="tested_candidate_isolated_pending_review"
                     and all(row.get(key)==value for key,value in expected.items()))
        summary_digest=hashlib.sha256(str(test_summary or "").encode("utf-8")).hexdigest()
        artifacts = []
        if not isinstance(installed_artifacts, list) or not installed_artifacts or len(installed_artifacts) > 5000:
            raise CapabilityGap("DEVOUR installation requires a bounded installed-artifact manifest")
        seen_paths = set()
        for item in installed_artifacts:
            if not isinstance(item, dict):
                raise CapabilityGap("Invalid installed-artifact manifest entry")
            rel = str(item.get("path", "")).replace("\\", "/")
            parts = rel.split("/")
            if (not rel or rel.startswith("/") or any(part in {"", ".", ".."} for part in parts)
                    or (len(rel) > 1 and rel[1] == ":") or rel in seen_paths):
                raise CapabilityGap("Unsafe or duplicate installed-artifact path")
            digest = self._sha256(item.get("sha256"), "installed artifact")
            size = item.get("size")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise CapabilityGap("Invalid installed-artifact size")
            seen_paths.add(rel)
            artifacts.append({"path": rel, "sha256": digest, "size": size})
        receipt["installation"]={
            "status":"installed_pending_runtime_verification",
            "version":validation["candidate_version"],
            "package_sha256":validation["candidate_sha256"],
            "post_update_test_summary_sha256":summary_digest,
            "rollback_backup_manifest_sha256":backup_digest,
            "installed_artifacts": artifacts,
            "installed_at":time.time(),
        }
        capability.version=validation["candidate_version"]
        capability.status=STATUS_UNVERIFIED
        capability.configured=False
        capability.verified=False
        capability.verification_note="Package tests passed; runtime registration and independent postcondition verification are still required."
        self._save()
        return {"recorded":True,"active":False,"verified":False,
                "status":"installed_pending_runtime_verification",
                "candidate_sha256":validation["candidate_sha256"]}

    def _devour_installation_intact(self, capability):
        """Revalidate promoted DEVOUR artifacts at claim time, not only at promotion."""
        if not (capability.source == "devour_review" or any(
            isinstance(row, dict) and row.get("source") == "devour"
            for row in capability.acquisition_evidence
        )):
            return True
        installation = None
        installation_receipt = None
        for receipt in reversed(capability.acquisition_evidence):
            candidate_installation = receipt.get("installation") if isinstance(receipt, dict) else None
            if (isinstance(candidate_installation, dict)
                    and candidate_installation.get("status") == "runtime_verified"):
                installation = candidate_installation
                installation_receipt = receipt
                break
        intact = bool(
            isinstance(installation, dict)
            and installation.get("version") == capability.version
            and installation.get("package_sha256")
            == (installation_receipt or {}).get("candidate_sha256")
        )
        artifacts = installation.get("installed_artifacts") if intact else None
        if not isinstance(artifacts, list) or not artifacts or len(artifacts) > 5000:
            intact = False
        runtime_check = installation.get("runtime_verification") if intact else None
        stored_identity = runtime_check.get("callable_provenance") if isinstance(runtime_check, dict) else None
        entry_point = normalize_entry_point((installation_receipt or {}).get("entry_point"))
        binding = self._runtime_callables.get(capability.name)
        live_identity = (
            self._bound_runtime_identity(capability.name, binding.get("function"))
            if isinstance(binding, dict) else None
        )
        if (not isinstance(stored_identity, dict) or not live_identity
                or stored_identity != live_identity
                or entry_point != f"{live_identity['module']}:{live_identity['qualname']}"):
            intact = False
        if intact:
            identity_artifact = next((row for row in artifacts if isinstance(row, dict)
                                      and str(row.get("path", "")).replace("\\", "/")
                                      == live_identity["source_path"]), None)
            if (identity_artifact is None
                    or identity_artifact.get("sha256") != live_identity["source_sha256"]
                    or identity_artifact.get("size") != live_identity["source_size"]):
                intact = False
        if intact:
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    intact = False
                    break
                rel = str(artifact.get("path", "")).replace("\\", "/")
                parts = rel.split("/")
                if (not rel or rel.startswith("/") or any(part in {"", ".", ".."} for part in parts)
                        or (len(rel) > 1 and rel[1] == ":")):
                    intact = False
                    break
                target = (self.root / Path(*parts)).resolve()
                try:
                    target.relative_to(self.root)
                    if (not target.is_file() or target.stat().st_size != artifact.get("size")
                            or hashlib.sha256(target.read_bytes()).hexdigest() != artifact.get("sha256")):
                        intact = False
                        break
                except (OSError, ValueError):
                    intact = False
                    break
        if not intact and capability.verified:
            capability.status = STATUS_UNVERIFIED
            capability.verified = False
            capability.configured = False
            capability.verification_note = (
                "Previously promoted DEVOUR installation no longer matches its recorded artifact identity; "
                "capability disabled pending operator review and re-verification."
            )
            self._save()
        return intact

    def has(self, name):
        c = self.capabilities.get(str(name).lower())
        if c is not None and not self._devour_installation_intact(c):
            return False
        return bool(c and c.enabled and c.configured and c.status in {STATUS_AVAILABLE, STATUS_DEGRADED})

    def get(self, name):
        c = self.capabilities.get(str(name).lower())
        return asdict(c) if c else None

    def inventory(self):
        return [asdict(x) for x in sorted(self.capabilities.values(), key=lambda c: c.name)]

    def status(self, name):
        c = self.capabilities.get(str(name).lower())
        if not c:
            return {"name": str(name), "known": False, "status": STATUS_UNAVAILABLE}
        return {
            "name": c.name,
            "known": True,
            "enabled": c.enabled,
            "configured": c.configured,
            "status": c.status,
            "verified": c.verified,
            "reliability": round(float(c.reliability), 4),
            "version": c.version,
            "dependencies": list(c.dependencies),
            "permissions": list(c.permissions),
            "alternatives": list(c.alternatives),
            "last_success": c.last_success,
            "last_failure": c.last_failure,
            "failure_count": c.failure_count,
            "success_count": c.success_count,
            "last_error": c.last_error,
            "verification_note": c.verification_note,
            "acquisition_evidence": [dict(row) for row in c.acquisition_evidence[-10:]],
        }

    def set_status(self, name, status, *, configured=None, verified=None, note=None):
        if status not in {STATUS_AVAILABLE, STATUS_DEGRADED, STATUS_UNAVAILABLE, STATUS_UNVERIFIED}:
            raise ValueError(f"Invalid capability status: {status}")
        c = self.capabilities.get(str(name).lower())
        if not c:
            raise CapabilityGap(f"Unknown capability: {name}")
        c.status = status
        if configured is not None:
            c.configured = bool(configured)
        if verified is not None:
            c.verified = bool(verified)
        if note is not None:
            c.verification_note = str(note)[:1000]
        self._save()
        return self.status(name)

    def record_success(self, name, *, reliability=None, note="", evidence_sha256="", observer="",
                       runtime_callable=None):
        c = self.capabilities.get(str(name).lower())
        if not c:
            raise CapabilityGap(f"Unknown capability: {name}")
        evidence_digest=str(evidence_sha256 or "").lower()
        if evidence_digest and (len(evidence_digest)!=64 or any(ch not in "0123456789abcdef" for ch in evidence_digest)):
            raise ValueError("Runtime postcondition evidence requires a valid SHA-256")
        now = time.time()
        installed_version = ""
        try:
            installed_version = (self.root / "VERSION.txt").read_text(encoding="utf-8").strip().splitlines()[0]
        except (OSError, IndexError):
            pass

        # A successful same-named runtime tool is not sufficient to activate a DEVOUR
        # candidate. Require the exact installed version and a pending per-capability
        # installation receipt before changing the capability's verified/available state.
        devour_managed = c.source == "devour_review" or any(
            isinstance(receipt, dict) and receipt.get("source") == "devour"
            for receipt in c.acquisition_evidence
        )
        pending_installation = None
        pending_callable_provenance = None
        promotion_block_reason = ""
        if devour_managed:
            if evidence_digest and str(observer or name) == name and installed_version == c.version:
                for receipt in reversed(c.acquisition_evidence):
                    installation = receipt.get("installation") if isinstance(receipt, dict) else None
                    if (isinstance(installation, dict)
                            and installation.get("status") == "installed_pending_runtime_verification"
                            and installation.get("version") == installed_version
                            and installation.get("package_sha256") == receipt.get("candidate_sha256")):
                        artifacts = installation.get("installed_artifacts")
                        if not isinstance(artifacts, list) or not artifacts or len(artifacts) > 5000:
                            continue
                        artifacts_match = True
                        for artifact in artifacts:
                            if not isinstance(artifact, dict):
                                artifacts_match = False
                                break
                            rel = str(artifact.get("path", ""))
                            parts = rel.replace("\\", "/").split("/")
                            if (not rel or rel.startswith("/") or any(part in {"", ".", ".."} for part in parts)
                                    or (len(rel) > 1 and rel[1] == ":")):
                                artifacts_match = False
                                break
                            target = (self.root / Path(*parts)).resolve()
                            try:
                                target.relative_to(self.root)
                                if (not target.is_file() or target.stat().st_size != artifact.get("size")
                                        or hashlib.sha256(target.read_bytes()).hexdigest() != artifact.get("sha256")):
                                    artifacts_match = False
                                    break
                            except (OSError, ValueError):
                                artifacts_match = False
                                break
                        if artifacts_match:
                            identity = self._bound_runtime_identity(name, runtime_callable)
                            entry_point = normalize_entry_point(receipt.get("entry_point"))
                            if identity is None:
                                promotion_block_reason = (
                                    "The executed callable is not the exact live ALICE tool registered for this capability."
                                )
                                continue
                            if entry_point != f"{identity['module']}:{identity['qualname']}":
                                promotion_block_reason = (
                                    "The executed callable does not match the candidate's declared ALICE entry point."
                                )
                                continue
                            identity_artifact = next((row for row in artifacts if isinstance(row, dict)
                                                      and str(row.get("path", "")).replace("\\", "/")
                                                      == identity["source_path"]), None)
                            if (identity_artifact is None
                                    or identity_artifact.get("sha256") != identity["source_sha256"]
                                    or identity_artifact.get("size") != identity["source_size"]):
                                promotion_block_reason = (
                                    "The registered callable's ALICE module is not bound to the installed candidate files."
                                )
                                continue
                            pending_installation = installation
                            pending_callable_provenance = identity
                            break
            if pending_installation is None:
                c.verification_note = (
                    "Runtime success observed, but DEVOUR promotion is blocked: "
                    + (promotion_block_reason or
                       "no matching installed DEVOUR candidate/version, declared entry point, "
                       "or independent capability postcondition is available.")
                )
                self._save()
                return self.status(name)

        c.last_success = now
        c.success_count += 1
        c.verified = True
        c.configured = True
        c.status = STATUS_AVAILABLE
        c.last_error = ""
        if reliability is None:
            total = c.success_count + c.failure_count
            reliability = c.success_count / total if total else 1.0
        c.reliability = max(0.0, min(1.0, float(reliability)))
        if note:
            c.verification_note = str(note)[:1000]
        if pending_installation is not None:
            pending_installation["runtime_verification"] = {
                "status": "independently_verified", "observer_tool": str(observer or name)[:100],
                "postcondition_evidence_sha256": evidence_digest, "verified_at": now,
                "callable_provenance": dict(pending_callable_provenance),
            }
            pending_installation["status"] = "runtime_verified"
        self._save()
        return self.status(name)

    def record_failure(self, name, error, *, degraded=True):
        c = self.capabilities.get(str(name).lower())
        if not c:
            raise CapabilityGap(f"Unknown capability: {name}")
        now = time.time()
        c.last_failure = now
        c.failure_count += 1
        c.last_error = str(error)[:1000]
        total = c.success_count + c.failure_count
        c.reliability = c.success_count / total if total else 0.0
        c.status = STATUS_DEGRADED if degraded and c.enabled and c.configured else STATUS_UNAVAILABLE
        self._save()
        return self.status(name)

    def alternatives_for(self, name):
        c = self.capabilities.get(str(name).lower())
        if not c:
            return []
        result = []
        for alt in c.alternatives:
            target = self.capabilities.get(alt)
            if target and target.enabled and target.configured and target.status in {STATUS_AVAILABLE, STATUS_DEGRADED}:
                result.append(alt)
        return result

    def can_claim(self, name):
        c = self.capabilities.get(str(name).lower())
        if c is not None and not self._devour_installation_intact(c):
            return False
        return bool(c and c.enabled and c.configured and c.verified and c.status == STATUS_AVAILABLE)

    def self_model(self):
        items = self.inventory()
        return {
            "capabilities": items,
            "available": [c["name"] for c in items if c["status"] == STATUS_AVAILABLE and c["enabled"] and c["configured"]],
            "degraded": [c["name"] for c in items if c["status"] == STATUS_DEGRADED],
            "unavailable": [c["name"] for c in items if c["status"] == STATUS_UNAVAILABLE or not c["enabled"] or not c["configured"]],
            "unverified": [c["name"] for c in items if not c["verified"]],
        }

    def gap(self, goal, known_tools):
        """Identify missing capabilities without delegating or executing anything."""
        import re
        # Tool names describe what ALICE already knows about. Including them in
        # the request made unrelated capabilities appear missing on every turn.
        text = str(goal or "").lower()
        hints = []
        mapping = {
            "software_building": ("code", "coding", "program", "script"),
            "browser_automation": ("website", "browser", "webpage"),
            "voice_io": ("voice", "microphone", "speech"),
            "computer_control": ("screenshot",),
            "web_research": ("research",),
        }
        for cap, terms in mapping.items():
            if any(re.search(r"\b" + re.escape(term) + r"\b", text) for term in terms) and not self.has(cap):
                hints.append(cap)
        return hints
