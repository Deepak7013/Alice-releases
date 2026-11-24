import pytest
from alice.ui.response_stream import ResponseStreamAssembler

def test_stream_assembles_exact_complete_response():
    s=ResponseStreamAssembler(); assert s.add("ALICE "); assert s.add("is ready.")
    result=s.finish()
    assert result.complete and result.text=="ALICE is ready." and result.chunks==2

def test_empty_stream_returns_explicit_nonblank_failure():
    result=ResponseStreamAssembler().finish()
    assert not result.complete and result.text and result.reason=="empty_stream"

def test_size_limit_discards_partial_response():
    s=ResponseStreamAssembler(max_chars=5); assert not s.add("123456")
    result=s.finish(); assert not result.complete and "safety limit" in result.text

def test_aborted_stream_does_not_leak_partial_text():
    s=ResponseStreamAssembler(); s.add("secret partial answer")
    result=s.abort("provider timeout")
    assert not result.complete and "secret partial" not in result.text and result.reason=="provider timeout"

def test_closed_stream_rejects_late_chunks():
    s=ResponseStreamAssembler(); s.add("done"); s.finish()
    assert not s.add("late")

def test_invalid_stream_limit_rejected():
    with pytest.raises(ValueError): ResponseStreamAssembler(max_chars=True)
