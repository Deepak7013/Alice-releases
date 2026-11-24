from __future__ import annotations
from pathlib import Path
import hashlib
class RegressionBaseline:
 def __init__(self,root): self.root=Path(root).resolve()
 def fingerprint(self,paths=None):
  chosen=[self.root/Path(x) for x in paths] if paths is not None else [p for p in self.root.rglob("*.py") if not any(x in {".git",".venv","alice_workspace","__pycache__"} for x in p.relative_to(self.root).parts)]
  h=hashlib.sha256()
  for p in sorted(chosen):
   if p.is_file(): h.update(p.relative_to(self.root).as_posix().encode()); h.update(p.read_bytes())
  return h.hexdigest()
 def matches(self,expected,paths=None): return self.fingerprint(paths)==str(expected)
