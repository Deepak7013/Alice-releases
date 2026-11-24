import os
from pathlib import Path

# The frozen desktop runtime is installed beneath Program Files, which is not
# writable by a standard user. Electron supplies ALICE_DATA_ROOT in the
# per-user profile; keep this shared file workspace there as well.
# Development runs retain the historical cwd-relative data/workspace folder.
_data_root = os.getenv("ALICE_DATA_ROOT", "").strip()
ROOT = (Path(_data_root).expanduser() / "workspace" if _data_root else Path("data/workspace")).resolve()
ROOT.mkdir(parents=True,exist_ok=True)

def safe_path(path):
    p=(ROOT/path).resolve()
    if ROOT not in p.parents and p!=ROOT:
        raise PermissionError("Path outside Alice workspace")
    return p

def list_files(path="."):
    return [str(x.relative_to(ROOT)) for x in safe_path(path).rglob("*") if x.is_file()]

def read_file(path):
    return safe_path(path).read_text(encoding="utf-8",errors="ignore")

def write_file(path,content):
    p=safe_path(path); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(content,encoding="utf-8")
    return str(p.relative_to(ROOT))
