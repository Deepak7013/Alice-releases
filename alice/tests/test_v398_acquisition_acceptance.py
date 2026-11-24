import pytest
from alice.engineering.acquisition_acceptance import evaluate

def test_complete_local_candidate_can_be_promoted():
    r=evaluate('vision',tests_required=3,tests_passed=3,sandbox_verified=True)
    assert r.promotion_allowed

def test_incomplete_tests_block():
    assert not evaluate('vision',tests_required=3,tests_passed=2,sandbox_verified=True).promotion_allowed

def test_sandbox_required():
    assert not evaluate('vision',tests_required=3,tests_passed=3,sandbox_verified=False).promotion_allowed

def test_external_needs_explicit_approval():
    assert not evaluate('vision',tests_required=3,tests_passed=3,sandbox_verified=True,external=True).promotion_allowed

def test_bad_counts_rejected():
    with pytest.raises(ValueError): evaluate('x',tests_required=2,tests_passed=3,sandbox_verified=True)
