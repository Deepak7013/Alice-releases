from alice.voice.cancellation import SpeechCancellation
from alice.voice.orchestrator import LocalSpeechOrchestrator

class Engine:
    name="local-test"; local_owned=True; remote_dependency=False; offline=True
    def __init__(self): self.calls=[]; self.stopped=0; self.cancel=None
    def can_generate(self,text): return bool(text)
    def speak(self,text):
        self.calls.append(text)
        if self.cancel is not None: self.cancel.cancel("test_stop")
        return True
    def stop(self): self.stopped+=1

def test_cancel_is_idempotent_and_calls_stop_callbacks_once():
    c=SpeechCancellation(); calls=[]; c.register_stop(lambda: calls.append(1))
    first=c.cancel("user stopped"); second=c.cancel("ignored")
    assert first.cancelled and first.callbacks_invoked==1 and second.callbacks_invoked==0
    assert calls==[1] and c.reason=="user stopped"

def test_register_after_cancel_runs_stop_immediately():
    c=SpeechCancellation(); c.cancel(); calls=[]; c.register_stop(lambda: calls.append(1))
    assert calls==[1]

def test_orchestrator_stops_before_next_segment_after_cancellation():
    e=Engine(); c=SpeechCancellation(); e.cancel=c
    result=LocalSpeechOrchestrator().run("First sentence. Second sentence.",engine=e,cancellation=c)
    assert result.reason=="speech_cancelled" and len(e.calls)==1
    assert result.next_segment_index==1 and e.stopped==1

def test_pre_cancelled_run_never_starts_speech():
    e=Engine(); c=SpeechCancellation(); c.cancel("before start")
    result=LocalSpeechOrchestrator().run("Hello there.",engine=e,cancellation=c)
    assert result.reason=="speech_cancelled" and not e.calls


def test_resume_after_cancel_does_not_replay_successful_segment():
    e = Engine(); c = SpeechCancellation(); e.cancel = c
    first = LocalSpeechOrchestrator().run("First sentence. Second sentence.", engine=e, cancellation=c)
    assert first.reason == "speech_cancelled" and first.next_segment_index == 1
    e.cancel = None
    resumed = LocalSpeechOrchestrator().run(
        "First sentence. Second sentence.", engine=e, start_segment=first.next_segment_index
    )
    assert resumed.reason == "speech_run_complete"
    assert e.calls == ["First sentence.", "Second sentence."]


def test_cancelled_failed_segment_keeps_resume_index_on_ambiguous_segment():
    class FailingEngine(Engine):
        def speak(self, text):
            self.calls.append(text)
            if self.cancel is not None:
                self.cancel.cancel("test_stop")
            return False
    e = FailingEngine(); c = SpeechCancellation(); e.cancel = c
    result = LocalSpeechOrchestrator().run("First sentence. Second sentence.", engine=e, cancellation=c)
    assert result.reason == "speech_cancelled"
    assert result.next_segment_index == 0
