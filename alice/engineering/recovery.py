from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class RecoveryReport:
 candidate_verified:bool; rollback_available:bool; promotion_eligible:bool; recovery_action:str
 def as_dict(self): return asdict(self)
def assess_recovery(candidate_verified,rollback_available,promotion_eligible):
 action='ready_for_explicit_promotion' if promotion_eligible and candidate_verified else ('rollback_candidate' if rollback_available else 'discard_candidate')
 return RecoveryReport(bool(candidate_verified),bool(rollback_available),bool(promotion_eligible),action)
