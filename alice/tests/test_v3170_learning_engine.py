from alice.learning.engine import LearningEngine


def test_learning_promotes_after_verified_successes(tmp_path):
    e = LearningEngine(tmp_path)
    for _ in range(3):
        e.record("create college presentation", "ppt_verified", True, verified=True, quality=.95)
    r = e.recommend("create college presentation")
    assert r and r[0]["workflow"] == "ppt_verified"
    assert r[0]["promoted"] is True


def test_learning_tracks_failure_and_regression(tmp_path):
    e = LearningEngine(tmp_path)
    for _ in range(3):
        e.record("fix python app", "safe_patch", True, verified=True, quality=.9)
    e.record("fix python app", "safe_patch", False, error="pytest failed", error_class="TestFailure")
    r = e.regressions()
    assert r and r[0]["workflow"] == "safe_patch"
    assert r[0]["consecutive_failures"] == 1
    assert r[0]["last_error"] == "pytest failed"


def test_failure_fingerprint_normalizes_numbers(tmp_path):
    a = LearningEngine.failure_fingerprint("timeout after 10 seconds", "Timeout")
    b = LearningEngine.failure_fingerprint("timeout after 20 seconds", "Timeout")
    assert a == b


def test_learning_consolidation_and_eval_cases(tmp_path):
    e = LearningEngine(tmp_path)
    e.record("research topic", "research_then_verify", True, verified=True, quality=.8)
    e.record("research topic", "research_then_verify", True, verified=True, quality=.9)
    s = e.consolidate()
    assert s["lesson_count"] == 1
    e.register_eval_case("research-basic", "research topic", expected="verified")
    e.grade_eval("research-basic", success=True, score=.9, notes="verified")
    assert e.stats()["eval_cases"] == 1
