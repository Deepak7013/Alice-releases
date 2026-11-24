from __future__ import annotations
import hashlib
from dataclasses import dataclass
from pathlib import Path
from .policy import TrustLevel
@dataclass(frozen=True)
class VerificationResult:
    verified: bool; digest: str; trust: TrustLevel; reasons: tuple[str,...]
class CapabilityVerifier:
    def digest_tree(self,path):
        p=Path(path); h=hashlib.sha256()
        files=[p] if p.is_file() else sorted(x for x in p.rglob('*') if x.is_file())
        for f in files:
            h.update(str(f.relative_to(p.parent if p.is_file() else p)).encode()); h.update(f.read_bytes())
        return h.hexdigest()
    def verify(self,path,expected_digest=None,trust=TrustLevel.UNTRUSTED):
        d=self.digest_tree(path); reasons=[]; ok=True
        if expected_digest:
            ok=d.lower()==expected_digest.lower(); reasons.append('digest matches expected value' if ok else 'digest mismatch')
        else:
            reasons.append('no signed/expected digest supplied'); ok=trust==TrustLevel.BUILTIN
        return VerificationResult(ok,d,trust if ok else TrustLevel.UNTRUSTED,tuple(reasons))
    def activation_allowed(self,result):
        return result.verified and result.trust in {TrustLevel.REVIEWED,TrustLevel.VERIFIED,TrustLevel.BUILTIN}
