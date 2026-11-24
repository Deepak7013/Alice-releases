import json
from pathlib import Path

from alice.deployment.updater import is_protected


def test_upgrade_manifest_contains_no_protected_paths():
    manifest_path = Path(__file__).parents[2] / "upgrade_manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    protected = [item["path"] for item in manifest.get("files", []) if is_protected(item.get("path", ""))]
    assert protected == []


def test_nested_security_tree_is_protected():
    assert is_protected("alice/alice/security/policy.py")
