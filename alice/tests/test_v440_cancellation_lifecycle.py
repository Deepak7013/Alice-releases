from alice.voice.cancellation import SpeechCancellation
from alice.voice.orchestrator import LocalSpeechOrchestrator

class Engine:
    name="local-test"; local_owned=True; remote_dependency=False; offline=True
    def __init__(self): self.calls=[]; self.stopped=0
    def can_generate(self,text): return bool(text)
    def speak(self,text): self.calls.append(text); return True
    def stop(self): self.stopped+=1

def test_completed_run_unregisters_stale_stop_callback():
    e=Engine(); c=SpeechCancellation()
    result=LocalSpeechOrchestrator().run("Hello there.",engine=e,cancellation=c)
    assert result.reason=="speech_run_complete" and e.calls
    cancelled=c.cancel("later")
    assert cancelled.callbacks_invoked==0 and e.stopped==0

def test_failed_run_unregisters_stop_callback():
    class Broken(Engine):
        def speak(self,text): self.calls.append(text); return False
    e=Broken(); c=SpeechCancellation()
    result=LocalSpeechOrchestrator().run("Hello there.",engine=e,cancellation=c)
    assert result.reason=="segment_execution_failed"
    assert c.cancel().callbacks_invoked==0 and e.stopped==0

def test_explicit_cancel_still_stops_active_engine():
    class Cancelling(Engine):
        def __init__(self,c): super().__init__(); self.c=c
        def speak(self,text): self.calls.append(text); self.c.cancel("user") ; return True
    c=SpeechCancellation();e=Cancelling(c)
    result=LocalSpeechOrchestrator().run("First sentence. Second sentence.",engine=e,cancellation=c)
    assert result.reason=="speech_cancelled" and e.stopped==1
