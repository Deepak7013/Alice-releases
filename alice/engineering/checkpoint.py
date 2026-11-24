"""Disposable candidate checkpoints and rollback."""
from __future__ import annotations
from pathlib import Path
import shutil, tempfile

class CandidateCheckpoint: 
    def __init__(self, candidate_root): self.root=Path(candidate_root).resolve(); self.slot=Path(tempfile.mkdtemp(prefix='alice_checkpoint_'))/'snapshot'
    def create(self):
        if self.slot.exists(): shutil.rmtree(self.slot)
        shutil.copytree(self.root,self.slot,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','.venv','.git','alice_workspace','*.pyc')); return self.slot
    def rollback(self):
        if not self.slot.exists(): raise FileNotFoundError('checkpoint_missing')
        for p in list(self.root.iterdir()):
            if p.name in {'.git','.venv','alice_workspace'}: continue
            if p.is_dir(): shutil.rmtree(p)
            else: p.unlink()
        for p in self.slot.iterdir():
            dst=self.root/p.name
            if p.is_dir(): shutil.copytree(p,dst)
            else: shutil.copy2(p,dst)
        return True
