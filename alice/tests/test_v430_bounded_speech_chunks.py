import pytest
from alice.voice.natural_pauses import plan_natural_pauses

def test_long_sentence_is_split_at_bounded_word_or_clause_boundaries():
    text = ("ALICE should preserve the complete answer, prepare the words carefully, "
            "keep the local voice responsive, and continue speaking without losing any content.")
    chunks = plan_natural_pauses(text, max_chars=48)
    assert len(chunks) > 1
    assert all(0 < len(chunk["text"]) <= 48 for chunk in chunks)
    assert " ".join(chunk["text"] for chunk in chunks) == text

def test_short_sentences_and_abbreviations_keep_prior_behavior():
    chunks = plan_natural_pauses("Dr. Rao arrived. Are we ready?")
    assert [c["text"] for c in chunks] == ["Dr. Rao arrived.", "Are we ready?"]
    assert chunks[1]["pause_ms"] == 300

def test_invalid_chunk_limits_are_rejected():
    with pytest.raises(ValueError): plan_natural_pauses("Hello there.", max_chars=10)
    with pytest.raises(ValueError): plan_natural_pauses("Hello there.", max_chars=True)

def test_empty_input_returns_no_chunks():
    assert plan_natural_pauses("") == []
