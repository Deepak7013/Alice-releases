from alice.evolution.self_improvement import SelfImprovementOrchestrator
from alice.engineering.models import EngineeringGoal
def test_self_improvement_stops_before_promotion(tmp_path):
 src=tmp_path/'src'; src.mkdir(); (src/'a.py').write_text('x=1\n',encoding='utf-8'); goal=EngineeringGoal('Improve','candidate improvement',['pass'])
 r=SelfImprovementOrchestrator().run('p1',goal,src,tmp_path/'work',[{'path':'a.py','content':'x=2\n'}],lambda _: (6,0),approval=True)
 assert r.verified and r.promotion_eligible and not r.promoted and (src/'a.py').read_text(encoding='utf-8')=='x=1\n'
