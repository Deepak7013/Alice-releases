from pathlib import Path
from alice.multimodal_agent import MultimodalAgentLoop, MultimodalGoal
from alice.creation.models import ArtifactKind

class FakeObservation:
    def to_dict(self): return {"summary":"ok"}
class FakeAnalyzer:
    def analyze(self, path, prompt): return FakeObservation()
class FakeArtifact:
    path="/tmp/alice-artifact.txt"; exists=True
class FakeCreator:
    def create(self, request): return FakeArtifact()
class FakeResearch:
    def research(self, q): return {"ok":True,"question":q}

def test_full_multimodal_loop(tmp_path):
    evidence=tmp_path/'e.txt'; evidence.write_text('evidence')
    loop=MultimodalAgentLoop(research=FakeResearch(), analyzer=FakeAnalyzer(), creator=FakeCreator())
    run=loop.execute(MultimodalGoal('make and verify a report', [str(evidence)], True, True, False, True))
    assert run.status=='completed'
    assert any(s.stage.value=='research' for s in run.steps)
    assert any(s.stage.value=='understand' for s in run.steps)
    assert any(s.stage.value=='create' for s in run.steps)
    assert any(s.stage.value=='verify' for s in run.steps)

def test_creation_context_selects_ai_agent():
    seen={}
    class C:
        def create(self, req): seen['kind']=req.kind; return FakeArtifact()
    loop=MultimodalAgentLoop(creator=C())
    run=loop.execute(MultimodalGoal('build an AI', create=True, research=False,
        context={'artifact_kind':ArtifactKind.AI_AGENT,'project_name':'agent'}))
    assert run.status=='completed' and seen['kind']==ArtifactKind.AI_AGENT

def test_action_is_delegated_without_bypassing_controller():
    seen={}
    def actor(goal, observations, artifact): seen['called']=True; return {'approved':True}
    loop=MultimodalAgentLoop(actor=actor)
    run=loop.execute(MultimodalGoal('do action', research=False, act=True))
    assert run.status=='completed' and seen['called']

def test_failed_verification_can_use_recovery():
    attempts={'n':0}
    def verify(*args): attempts['n']+=1; return False
    def recover(run, exc): return {'retry_planned':True}
    loop=MultimodalAgentLoop(verifier=verify, recovery=recover)
    run=loop.execute(MultimodalGoal('verify', research=False, verify=True, max_recoveries=1))
    assert run.status=='running' and run.recoveries==1
    assert run.steps[-1].stage.value=='recover'
