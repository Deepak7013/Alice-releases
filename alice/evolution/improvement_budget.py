from dataclasses import dataclass
@dataclass
class ImprovementBudget:
    max_steps:int=3; max_failures:int=1; steps_used:int=0; failures:int=0
    def can_continue(self): return self.steps_used < self.max_steps and self.failures <= self.max_failures
    def consume_step(self):
        if not self.can_continue(): return False
        self.steps_used += 1; return True
    def record_failure(self): self.failures += 1
    def reset(self): self.steps_used=0; self.failures=0
