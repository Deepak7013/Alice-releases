from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json
from pathlib import Path

@dataclass(frozen=True)
class UpgradeAttestation:
    version:str; manifest_sha256:str; parent_version:str; ok:bool
    def as_dict(self): return asdict(self)

def attest(root,parent_version=''):
    root=Path(root); vp=(root/'VERSION.txt').read_text(encoding='utf-8').strip() if (root/'VERSION.txt').exists() else ''
    mp=root/'full_install_manifest.json'
    if not mp.exists(): return UpgradeAttestation(vp,'',str(parent_version),False)
    digest=hashlib.sha256(mp.read_bytes()).hexdigest()
    ok=vp.startswith('ALICE v') and bool(parent_version) and vp != str(parent_version).strip()
    return UpgradeAttestation(vp,digest,str(parent_version),ok)
