from alice.ui.canonical_response import CanonicalResponseStore
from alice.ui.response_transaction import ResponseTransaction

def test_canonical_store_preserves_stream_order():
    s=CanonicalResponseStore(); s.begin("x"); s.append("x","A"); s.append("x","B"); r=s.finish("x")
    assert r.text=="AB" and r.status=="completed" and r.speakable

def test_canonical_store_partial_failure_is_recoverable():
    s=CanonicalResponseStore(); s.begin("x"); s.append("x","partial"); r=s.fail("x")
    assert r.text=="partial" and r.recoverable and not r.speakable

def test_response_transaction_uses_canonical_store():
    tx=ResponseTransaction(); tx.append("one"); tx.append(" two"); r=tx.complete()
    assert r.completed and tx.text=="one two" and tx._canonical is not None
