from alice.voice.execution_boundary import LocalVoiceExecutionBoundary


class Engine:
    name = "local"
    offline = True

    def __init__(self, result=True):
        self.result = result
        self.spoken = []

    def can_generate(self, text):
        return bool(text)

    def speak(self, text):
        self.spoken.append(text)
        return self.result


def test_execution_boundary_requires_text():
    result = LocalVoiceExecutionBoundary().execute(Engine(), "")
    assert result.attempted is False
    assert result.reason == "text_missing"


def test_execution_boundary_executes_admitted_local_engine():
    engine = Engine()
    result = LocalVoiceExecutionBoundary().execute(engine, "Hello ALICE.")
    assert result.attempted is True
    assert result.succeeded is True
    assert engine.spoken == ["Hello ALICE."]


def test_execution_boundary_rejects_remote_engine():
    class Remote:
        name = "remote"
        offline = False
        def can_generate(self, text):
            return True
        def speak(self, text):
            raise AssertionError("remote engine must not execute")
    result = LocalVoiceExecutionBoundary().execute(Remote(), "Hello")
    assert result.attempted is False
    assert result.reason == "offline_capability_required"


def test_execution_boundary_surfaces_engine_failure():
    result = LocalVoiceExecutionBoundary().execute(Engine(False), "Hello")
    assert result.attempted is True
    assert result.succeeded is False
    assert result.reason == "engine_reported_failure"
