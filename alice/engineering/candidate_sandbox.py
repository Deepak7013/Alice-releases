"""Side-effect-bounded candidate workspace for self-engineering."""
from __future__ import annotations
from pathlib import Path
import shutil, tempfile

class CandidateSandbox:
    PROTECTED={".env","alice_workspace",".git",".venv"}
    def __init__(self, source_root, workspace_root=None):
        self.source=Path(source_root).resolve(); self.base=Path(workspace_root or tempfile.mkdtemp(prefix="alice_candidate_")).resolve()
        self.path=self.base/"candidate"
    def create(self):
        if self.path.exists(): shutil.rmtree(self.path)
        shutil.copytree(self.source,self.path,ignore=shutil.ignore_patterns("__pycache__",".pytest_cache",".venv",".git","alice_workspace","*.pyc"))
        return self.path
    def _safe(self, rel):
        p=Path(str(rel).replace("\\","/"));
        if p.is_absolute() or ".." in p.parts or any(x in self.PROTECTED for x in p.parts): raise PermissionError("protected or escaping candidate path")
        out=(self.path/p).resolve()
        if self.path not in out.parents and out!=self.path: raise PermissionError("candidate path escape")
        return out
    def apply(self, changes):
        if not self.path.exists(): self.create()
        touched=[]
        for item in changes:
            p=self._safe(item["path"]); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(str(item.get("content","")),encoding="utf-8"); touched.append(p.relative_to(self.path).as_posix())
        return touched
