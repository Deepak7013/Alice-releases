from alice.voice.orchestrator import LocalSpeechOrchestrator


class Engine:
    name = "local"
    offline = True
    local_owned = True
    remote_dependency = False

    def __init__(self, fail_on=None):
        self.spoken = []
        self.fail_on = fail_on

    def can_generate(self, text):
        return bool(text)

    def speak(self, text):
        self.spoken.append(text)
        return text != self.fail_on


def test_orchestrator_runs_all_prepared_segments():
    engine = Engine()
    result = LocalSpeechOrchestrator().run("Hello. How are you?", engine=engine)
    assert result.prepared is True
    assert result.reason == "speech_run_complete"
    assert result.executed_segments == 2
    assert result.failed_segments == 0
    assert engine.spoken == ["Hello.", "How are you?"]


def test_orchestrator_stops_at_first_failed_segment():
    engine = Engine("How are you?")
    result = LocalSpeechOrchestrator().run("Hello. How are you? Next.", engine=engine)
    assert result.prepared is True
    assert result.reason == "segment_execution_failed"
    assert result.executed_segments == 1
    assert result.failed_segments == 1
    assert engine.spoken == ["Hello.", "How are you?"]


def test_orchestrator_never_executes_remote_engine():
    class Remote(Engine):
        offline = False
        local_owned = False
        remote_dependency = True

    engine = Remote()
    result = LocalSpeechOrchestrator().run("Hello.", engine=engine)
    assert result.prepared is False
    assert result.reason == "local_engine_required"
    assert engine.spoken == []


def test_orchestrator_preserves_pronunciation_preparation():
    engine = Engine()
    result = LocalSpeechOrchestrator().run(
        "ALICE says GPU.", engine=engine, pronunciation={"GPU": "G P U"}
    )
    assert result.prepared is True
    assert engine.spoken == ["ALICE says G P U."]
