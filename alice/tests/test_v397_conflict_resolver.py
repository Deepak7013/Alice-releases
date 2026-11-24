from alice.learning.conflict_resolver import LearningConflictResolver

def test_accept_without_existing():
    r=LearningConflictResolver().resolve('x','', 'new')
    assert r.decision=='accept'

def test_higher_confidence_supersedes():
    r=LearningConflictResolver().resolve('x','old','new',existing_confidence=.5,incoming_confidence=.8)
    assert r.decision=='supersede'

def test_tie_requires_review():
    r=LearningConflictResolver().resolve('x','old','new',existing_confidence=.7,incoming_confidence=.7)
    assert r.decision=='review'

def test_duplicate_is_inert():
    r=LearningConflictResolver().resolve('x','same','same',existing_confidence=.9,incoming_confidence=.1)
    assert r.decision=='duplicate'
