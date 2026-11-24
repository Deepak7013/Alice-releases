from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import shutil,tempfile
@dataclass
class ChangeReview:
    allowed:bool; reason:str; backup:str|None=None; digest_before:str|None=None
class EvolutionGovernor:
    """Controlled source changes: protected paths, backup, digest, and explicit test result."""
    def __init__(self, protected=('alice/security','alice/evolution')): self.protected=tuple(protected)
    def review(self, path, root):
        p=(Path(root)/path).resolve(); base=Path(root).resolve()
        try:p.relative_to(base)
        except ValueError:return ChangeReview(False,'path escapes source root')
        rel=p.relative_to(base).as_posix()
        if any(rel==x or rel.startswith(x+'/') for x in self.protected): return ChangeReview(False,'protected source path')
        if not p.exists() or not p.is_file(): return ChangeReview(False,'source file not found')
        digest=sha256(p.read_bytes()).hexdigest(); backup=str(p.with_suffix(p.suffix+'.bak'))
        shutil.copy2(p,backup)
        return ChangeReview(True,'reviewed; backup created',backup,digest)
    def rollback(self, review:ChangeReview, target):
        if not review.backup: raise ValueError('no backup')
        shutil.copy2(review.backup,target)
