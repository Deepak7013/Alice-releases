from alice.voice.natural_pauses import plan_natural_pauses

def test_abbreviation_does_not_create_false_sentence_boundary():
    chunks=plan_natural_pauses("Dr. Rao arrived. We started.")
    assert [x["text"] for x in chunks] == ["Dr. Rao arrived.", "We started."]

def test_decimal_and_version_numbers_do_not_split_sentences():
    chunks=plan_natural_pauses("Use version 4.29.0. The value is 3.14 today.")
    assert [x["text"] for x in chunks] == ["Use version 4.29.0.", "The value is 3.14 today."]

def test_common_latin_abbreviations_remain_inside_sentence():
    chunks=plan_natural_pauses("Use e.g. local engines, i.e. offline engines. Continue now.")
    assert [x["text"] for x in chunks] == ["Use e.g. local engines, i.e. offline engines.", "Continue now."]

def test_empty_and_normal_sentence_boundaries_remain_stable():
    assert plan_natural_pauses("  ") == []
    chunks=plan_natural_pauses("Ready? Yes! Good.")
    assert [x["text"] for x in chunks] == ["Ready?", "Yes!", "Good."]


def test_abbreviation_rule_does_not_match_inside_ordinary_words():
    chunks=plan_natural_pauses("First. Last. Next.")
    assert [x["text"] for x in chunks] == ["First.", "Last.", "Next."]
