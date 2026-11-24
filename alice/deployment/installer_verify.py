"""Verify an ALICE full-installer tree against its embedded manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

MANIFEST = "full_install_manifest.json"
SKIP_PARTS = {".venv", ".git", ".alice_backups", "__pycache__", ".pytest_cache", "alice_workspace", "data"}
# Upgrade manifests are transaction-specific control metadata. They are
# signed and verified separately by the updater, so hashing one into the
# immutable full-install inventory creates a circular/stale-manifest issue
# when an in-place update replaces it.
SKIP_FILES = {".env", "ALICE_INSTALL.log", "upgrade_manifest.json"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts = set(Path(rel).parts)
        if (
            rel == MANIFEST
            or parts & SKIP_PARTS
            or any(part.startswith(".venv") for part in parts)
            or Path(rel).name in SKIP_FILES
        ):
            continue
        yield rel, p


def verify(root) -> dict:
    root = Path(root).resolve()
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        return {"ok": False, "reason": "manifest_missing"}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {str(x["path"]): x for x in manifest["files"]}
    except Exception as exc:
        return {"ok": False, "reason": "manifest_invalid", "error": str(exc)[:300]}

    actual = {rel: p for rel, p in _iter_files(root)}
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    mismatched = []
    for rel in sorted(set(expected) & set(actual)):
        row = expected[rel]
        p = actual[rel]
        if int(row.get("size", -1)) != p.stat().st_size or str(row.get("sha256")) != sha256(p):
            mismatched.append(rel)
    return {
        "ok": not missing and not unexpected and not mismatched,
        "version": manifest.get("version", ""),
        "manifest_files": len(expected),
        "actual_files": len(actual),
        "missing": missing,
        "unexpected": unexpected,
        "mismatched": mismatched,
    }


def build_manifest(root) -> dict:
    """Create the immutable file/hash inventory used by a full installer ZIP."""
    root = Path(root).resolve()
    version_path = root / "VERSION.txt"
    version = version_path.read_text(encoding="utf-8").strip().splitlines()[0] if version_path.is_file() else ""
    files = [
        {"path": rel, "size": path.stat().st_size, "sha256": sha256(path)}
        for rel, path in sorted(_iter_files(root), key=lambda row: row[0])
    ]
    return {"format": 1, "product": "ALICE", "version": version, "files": files}


def write_manifest(root) -> dict:
    """Atomically refresh and immediately verify the current full-installer manifest."""
    root = Path(root).resolve()
    target = root / MANIFEST
    payload = json.dumps(build_manifest(root), indent=2, ensure_ascii=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=root, prefix=MANIFEST + ".", suffix=".tmp", delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    result = verify(root)
    if not result.get("ok"):
        raise RuntimeError("Generated full-installer manifest did not verify: " + json.dumps(result))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--write-manifest", action="store_true",
                    help="refresh the manifest before verifying the installer tree")
    args = ap.parse_args()
    result = write_manifest(args.root) if args.write_manifest else verify(args.root)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()
