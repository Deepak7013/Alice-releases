"""Load the non-secret ALICE project baseline into the local workspace once."""
from __future__ import annotations
from pathlib import Path

TARGET = "ALICE_PROJECT_BASELINE.md"

def ensure_baseline(root=None):
    root=Path(root or Path(__file__).resolve().parents[2]).resolve()
    target=root/"alice_workspace"/TARGET
    if target.exists():
        return target
    source=root/TARGET
    if source.is_file():
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"),encoding="utf-8")
        return target
    return None

def read_baseline(root=None, max_chars=12000):
    path=ensure_baseline(root)
    if not path or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")[-max_chars:]
