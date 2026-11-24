from alice.engineering.cycle import GovernedEngineeringCycle
from alice.engineering.models import EngineeringGoal

def test_cycle_builds_and_validates_candidate_without_promotion(tmp_path):
    src=tmp_path/'src'; src.mkdir(); (src/'a.py').write_text('x=1\n',encoding='utf-8')
    goal=EngineeringGoal('Fix test','Improve reliability',['tests pass'])
    r=GovernedEngineeringCycle().run('p1',goal,src,tmp_path/'work',[{'path':'a.py','content':'x=2\n'}],lambda _: (5,0))
    assert r.verified and r.tests_passed==5 and r.promoted is False
    assert (src/'a.py').read_text(encoding='utf-8')=='x=1\n'
