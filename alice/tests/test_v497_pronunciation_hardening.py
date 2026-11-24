from alice.voice.text_prep import apply_pronunciation


def test_non_dictionary_and_malformed_entries_fail_closed():
    assert apply_pronunciation('Hello', ['Hello', 'Hi']) == 'Hello'
    assert apply_pronunciation('Hello world', {None: 'bad', 'Hello': None, 'world': 'Earth'}) == 'Hello Earth'


def test_replacement_text_is_literal_and_cannot_be_interpreted_as_regex():
    value = apply_pronunciation('Use C++ and A.B.', {'C++': 'C plus plus', 'A.B.': 'A dot B'})
    assert value == 'Use C plus plus and A dot B'


def test_longest_phrase_precedes_shorter_term_and_does_not_rewrite_inserted_text():
    value = apply_pronunciation('OpenAI API; OpenAI.', {'OpenAI API': 'Open A I A P I', 'OpenAI': 'Open A I', 'API': 'A P I'})
    assert value == 'Open A I A P I; Open A I.'


def test_control_characters_and_oversized_entries_are_ignored():
    value = apply_pronunciation('ALICE Good', {'ALICE': 'A L I C E', 'Bad\nKey': 'x', 'Good': 'x' * 201})
    assert value == 'A L I C E Good'
