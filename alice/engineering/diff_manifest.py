from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json
@dataclass(frozen=True)
class CandidateDiffManifest:
 files:list[str]; digest:str; changed_lines:int
 def as_dict(self): return asdict(self)
def make_manifest(impact):
 files=sorted(str(x) for x in impact.get('files',[])); payload={'files':files,'changed_lines':int(impact.get('changed_lines',0))}; digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
 return CandidateDiffManifest(files,digest,payload['changed_lines'])
