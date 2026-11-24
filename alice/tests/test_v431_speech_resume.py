from alice.voice.orchestrator import LocalSpeechOrchestrator

class Engine:
    name="local"; offline=True; local_owned=True; remote_dependency=False
    def __init__(self, fail_on=None): self.spoken=[]; self.fail_on=fail_on
    def can_generate(self,text): return bool(text)
    def speak(self,text): self.spoken.append(text); return text != self.fail_on

def test_failure_checkpoint_resumes_without_replaying_successful_segments():
    engine=Engine("Second."); orchestrator=LocalSpeechOrchestrator()
    first=orchestrator.run("First. Second. Third.",engine=engine)
    assert first.reason=="segment_execution_failed" and first.next_segment_index==1
    engine.fail_on=None
    resumed=orchestrator.run("First. Second. Third.",engine=engine,start_segment=first.next_segment_index)
    assert resumed.reason=="speech_run_complete" and resumed.next_segment_index==3
    assert engine.spoken==["First.","Second.","Second.","Third."]

def test_resume_index_is_validated():
    engine=Engine(); o=LocalSpeechOrchestrator()
    assert o.run("Hello.",engine=engine,start_segment=-1).reason=="resume_index_out_of_range"
    assert o.run("Hello.",engine=engine,start_segment=True).reason=="invalid_resume_index"
    assert engine.spoken==[]

def test_completed_run_points_to_end_of_directive():
    result=LocalSpeechOrchestrator().run("One. Two.",engine=Engine())
    assert result.reason=="speech_run_complete" and result.next_segment_index==2
