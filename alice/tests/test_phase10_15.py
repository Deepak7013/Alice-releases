from pathlib import Path
from alice.verification import ObserveVerifyRecover, Observation
from alice.acquisition.safe_devour import SafeDevour
from alice.self_engineering import SelfEngineering, EngineeringStage
from alice.learning import LearningStore
from alice.device_runtime import DeviceRuntime
from alice.final_integration import AliceIntegratedExecutive

def test_recovery_bounded_and_verifies():
    state={'ok':False,'n':0}
    def obs(): return Observation('x',state['n'],matches=state['ok'])
    def rec(): state['n']+=1; state['ok']=True
    r=ObserveVerifyRecover(2).run(obs,rec)
    assert r.verified and r.recovered and r.attempts==1

def test_recovery_does_not_loop_forever():
    r=ObserveVerifyRecover(2).run(lambda:Observation('x',0,matches=False),lambda:None)
    assert not r.verified and r.attempts==2

def test_devour_never_executes(tmp_path):
    import zipfile
    p=tmp_path/'devour.zip'
    with zipfile.ZipFile(p,'w') as z: z.writestr('agent.py','print(1)')
    r=SafeDevour().inspect_zip(p)
    assert not r.executed and r.files==1 and r.sha256

def test_engineering_requires_tests_before_promotion():
    e=SelfEngineering(); r=e.start('bug'); e.advance(r,EngineeringStage.DIAGNOSE); e.advance(r,EngineeringStage.REPAIR); e.advance(r,EngineeringStage.TEST); e.advance(r,EngineeringStage.PACKAGE); e.advance(r,EngineeringStage.PROMOTE); assert r.promoted

def test_learning_persists(tmp_path):
    p=tmp_path/'memory.json'; s=LearningStore(p); s.learn('rule','remember bugs'); t=LearningStore(p); t.load(); assert t.get('rule').value=='remember bugs'

def test_device_registry_does_not_equate_registration_with_verification():
    d=DeviceRuntime(); c=d.register('voice',available=True); assert c.available and not c.verified

def test_integrated_executive_requires_verification_for_learning(tmp_path):
    s=LearningStore(tmp_path/'m.json'); e=AliceIntegratedExecutive(s); state={'ok':True}; r=e.complete(lambda:None,lambda:Observation('done',1,matches=state['ok']),lesson=('x','y')); assert r.verified and r.learned and s.get('x')
