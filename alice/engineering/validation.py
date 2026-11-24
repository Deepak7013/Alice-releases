"""Deterministic validation for isolated engineering candidates."""
from __future__ import annotations
import compileall
from pathlib import Path
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class CandidateValidation:
    syntax_ok: bool
    tests_passed: int
    tests_failed: int
    verified: bool
    errors: list[str]
    def as_dict(self): return asdict(self)

class CandidateValidator:
    def validate(self, candidate_root, test_fn=None):
        root=Path(candidate_root).resolve(); errors=[]
        syntax_ok=bool(compileall.compile_dir(str(root),quiet=1,force=False))
        if not syntax_ok: errors.append("syntax_validation_failed")
        passed=failed=0
        if test_fn is not None:
            result=test_fn(str(root)); passed,failed=int(result[0]),int(result[1])
            if failed: errors.append("candidate_tests_failed")
        return CandidateValidation(syntax_ok,passed,failed,bool(syntax_ok and failed==0),errors)
