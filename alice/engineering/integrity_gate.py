from __future__ import annotations
from dataclasses import dataclass,asdict
from .regression import RegressionBaseline
@dataclass(frozen=True)
class IntegrityResult:
 impact_ok:bool; regression_ok:bool; protected_ok:bool; eligible:bool; reasons:list[str]
 def as_dict(self): return asdict(self)
class IntegrityGate:
 def evaluate(self,impact,baseline=None,current=None,protected_ok=True):
  reasons=[]; impact_ok=bool(impact) and impact.get('risk') not in {'blocked','high'}
  if not impact_ok: reasons.append('impact_not_acceptable')
  regression_ok=True
  if baseline is not None and current is not None: regression_ok=str(baseline)==str(current)
  if not regression_ok: reasons.append('regression_baseline_mismatch')
  if not protected_ok: reasons.append('protected_boundary_failed')
  return IntegrityResult(impact_ok,regression_ok,bool(protected_ok),not reasons,reasons)
