"""Integrity verification for ALICE-owned local voice model artifacts."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path
from collections.abc import Mapping, Sequence

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_MODEL_ARTIFACTS = 512
MAX_ARTIFACT_NAME_CHARS = 160
MAX_ARTIFACT_PATH_CHARS = 512

@dataclass(frozen=True)
class ArtifactCheck:
    name: str
    ok: bool
    reason: str
    path: str | None = None

@dataclass(frozen=True)
class LocalModelVerification:
    ok: bool
    checked: int
    failed: int
    artifacts: tuple[ArtifactCheck, ...]
    reason: str
    manifest_digest: str | None = None


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_local_model_manifest(model_root: str | Path, artifacts: Sequence[Mapping[str, object]]) -> LocalModelVerification:
    """Verify listed files are contained in model_root and match SHA-256.

    This function performs no downloads, model loading, inference, or execution.
    Artifact paths must be relative; symlink resolution is checked against the
    resolved root to prevent a manifest entry escaping the approved directory.
    """
    try:
        root = Path(model_root).expanduser().resolve(strict=True)
    except Exception:
        return LocalModelVerification(False, 0, 1, (), "model_root_unavailable")
    if not root.is_dir():
        return LocalModelVerification(False, 0, 1, (), "model_root_not_directory")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, (str, bytes, bytearray)) or not artifacts:
        return LocalModelVerification(False, 0, 1, (), "artifact_manifest_empty_or_invalid")
    if len(artifacts) > MAX_MODEL_ARTIFACTS:
        return LocalModelVerification(False, 0, 1, (), "artifact_manifest_too_large")
    # Bind audit output to canonical manifest metadata, independent of row order.
    canonical_rows = []
    for row in artifacts:
        if isinstance(row, Mapping):
            canonical_rows.append({
                "name": str(row.get("name", "") or "").strip(),
                "path": str(row.get("path", "") or "").strip(),
                "sha256": str(row.get("sha256", "") or "").strip().lower(),
            })
        else:
            canonical_rows.append({"invalid_entry": type(row).__name__})
    canonical_rows.sort(key=lambda x: json.dumps(x, sort_keys=True, separators=(",", ":")))
    manifest_bytes = json.dumps(canonical_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    checks: list[ArtifactCheck] = []
    seen_paths: set[str] = set()
    seen_names: set[str] = set()
    for row in artifacts:
        if not isinstance(row, Mapping):
            checks.append(ArtifactCheck("", False, "artifact_entry_invalid")); continue
        name = str(row.get("name", "") or "").strip()
        rel_text = str(row.get("path", "") or "").strip()
        expected = str(row.get("sha256", "") or "").strip().lower()
        if (not name or len(name) > MAX_ARTIFACT_NAME_CHARS or not rel_text
                or len(rel_text) > MAX_ARTIFACT_PATH_CHARS or not _SHA256.fullmatch(expected)):
            checks.append(ArtifactCheck(name, False, "artifact_metadata_invalid")); continue
        # Reject Windows-specific absolute paths and separators even when the
        # verifier runs on POSIX; manifests must be portable and unambiguous.
        if "\\" in rel_text or re.match(r"^[A-Za-z]:", rel_text) or rel_text.startswith("//"):
            checks.append(ArtifactCheck(name, False, "artifact_path_not_relative_safe")); continue
        rel = Path(rel_text)
        if rel.is_absolute() or any(part in ("..", ".", "") for part in rel.parts):
            checks.append(ArtifactCheck(name, False, "artifact_path_not_relative_safe")); continue
        normalized_path = rel.as_posix().casefold()
        normalized_name = name.casefold()
        if normalized_name in seen_names:
            checks.append(ArtifactCheck(name, False, "duplicate_artifact_name")); continue
        if normalized_path in seen_paths:
            checks.append(ArtifactCheck(name, False, "duplicate_artifact_path")); continue
        seen_names.add(normalized_name)
        seen_paths.add(normalized_path)
        try:
            target = (root / rel).resolve(strict=True)
            if not target.is_relative_to(root):
                checks.append(ArtifactCheck(name, False, "artifact_path_escape")); continue
            if not target.is_file():
                checks.append(ArtifactCheck(name, False, "artifact_not_file", str(target))); continue
            actual = _digest(target)
            if actual != expected:
                checks.append(ArtifactCheck(name, False, "artifact_hash_mismatch", str(target)))
            else:
                checks.append(ArtifactCheck(name, True, "artifact_verified", str(target)))
        except FileNotFoundError:
            checks.append(ArtifactCheck(name, False, "artifact_missing"))
        except Exception:
            checks.append(ArtifactCheck(name, False, "artifact_verification_failed"))
    failed = sum(not x.ok for x in checks)
    return LocalModelVerification(failed == 0 and bool(checks), len(checks), failed, tuple(checks),
                                  "local_model_manifest_verified" if failed == 0 and checks else "local_model_manifest_rejected",
                                  manifest_digest)
