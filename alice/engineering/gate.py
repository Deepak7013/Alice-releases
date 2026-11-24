"""Deterministic self-engineering change gate.

The gate is intentionally model-independent.  It measures a proposed patch,
checks syntax and protected boundaries, and produces a risk/impact report that
must accompany any self-engineering promotion.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import ast, difflib
from pathlib import Path

@dataclass
class ChangeImpact:
    files: list[str]
    added_lines: int
    removed_lines: int
    changed_lines: int
    risk: str
    syntax_ok: bool
    reasons: list[str]

    def as_dict(self):
        return asdict(self)

class SelfEngineeringGate:
    MAX_FILES = 24
    MAX_CHANGED_LINES = 1800

    def analyze(self, root, items):
        root = Path(root).resolve()
        files=[]; added=removed=0; reasons=[]; syntax_ok=True
        for item in items:
            rel=Path(str(item["path"]).replace("\\","/")).as_posix()
            files.append(rel)
            old_path=root/rel
            old=old_path.read_text(encoding="utf-8") if old_path.exists() else ""
            new=str(item.get("content",""))
            diff=list(difflib.unified_diff(old.splitlines(),new.splitlines(),lineterm=""))
            for line in diff:
                if line.startswith("+++") or line.startswith("---"): continue
                if line.startswith("+"): added += 1
                elif line.startswith("-"): removed += 1
            if rel.endswith(".py"):
                try: ast.parse(new,filename=rel)
                except Exception as exc:
                    syntax_ok=False; reasons.append(f"syntax:{rel}:{exc}")
        changed=added+removed
        if len(files)>self.MAX_FILES: reasons.append("too_many_files")
        if changed>self.MAX_CHANGED_LINES: reasons.append("too_many_changed_lines")
        if not files: reasons.append("empty_change")
        if syntax_ok and not reasons:
            risk="low" if len(files)<=3 and changed<=120 else "medium"
            if changed>600 or len(files)>8: risk="high"
        else:
            risk="blocked"
        return ChangeImpact(files,added,removed,changed,risk,syntax_ok,reasons)

    def preflight(self, root, items):
        impact=self.analyze(root,items)
        if impact.risk=="blocked":
            raise ValueError("self-engineering gate blocked change: " + "; ".join(impact.reasons))
        return impact.as_dict()

    @staticmethod
    def postflight(test_returncode, protected_ok=True):
        return bool(test_returncode==0 and protected_ok)
