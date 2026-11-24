from alice.evolution.improvement_budget import ImprovementBudget
def test_budget_bounds():
 b=ImprovementBudget(max_steps=2,max_failures=1); assert b.consume_step() and b.consume_step() and not b.consume_step()
def test_failure_limit():
 b=ImprovementBudget(max_steps=5,max_failures=1); b.record_failure(); assert b.can_continue(); b.record_failure(); assert not b.can_continue()
def test_reset():
 b=ImprovementBudget(max_steps=1,max_failures=0); b.consume_step(); b.reset(); assert b.consume_step()
