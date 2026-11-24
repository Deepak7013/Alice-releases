from alice.voice.speech_director import SpeechDirector


class LocalEngine:
    name = "local-test"
    local_owned = True
    offline = True
    remote_dependency = False


def test_director_builds_prepared_segmented_directive():
    result = SpeechDirector().prepare(
        "Hello, **ALICE**. How are you?",
        engine=LocalEngine(),
        pronunciation={"ALICE": "Alice"},
    )
    assert result.valid is True
    assert result.reason == "speech_directive_ready"
    assert result.engine == "local-test"
    assert result.text == "Hello, Alice. How are you?"
    assert [item["text"] for item in result.segments] == ["Hello, Alice.", "How are you?"]
    assert result.prosody.valid is True


def test_director_rejects_remote_engine():
    class Remote:
        name = "remote"
        local_owned = False
        offline = False
        remote_dependency = True

    result = SpeechDirector().prepare("hello", engine=Remote())
    assert result.valid is False
    assert result.reason == "local_engine_required"


def test_director_rejects_missing_engine():
    result = SpeechDirector().prepare("hello", engine=None)
    assert result.valid is False
    assert result.reason == "engine_missing"


def test_director_is_side_effect_free_for_engine():
    engine = LocalEngine()
    result = SpeechDirector().prepare("One. Two!", engine=engine, profile="casual", urgency=0.2)
    assert result.valid is True
    assert engine.name == "local-test"
