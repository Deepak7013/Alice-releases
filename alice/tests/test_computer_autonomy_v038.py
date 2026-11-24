from alice.computer_autonomy import ComputerActionController, ComputerAutonomyLoop
class B:
    def __init__(self): self.n=0
    def observe(self): return {"n":self.n}
    def click(self, x=0): self.n+=1; return "clicked"

def test_observe_act_verify_loop():
    b=B(); c=ComputerActionController(b)
    loop=ComputerAutonomyLoop(c, planner=lambda g,before,steps:{"name":"click","args":{"x":1}}, verifier=lambda g,s,r:s.after["n"]==1)
    r=loop.run("click once")
    assert r.status=="completed" and len(r.steps)==1

def test_no_action_becomes_waiting():
    b=B(); c=ComputerActionController(b)
    r=ComputerAutonomyLoop(c, planner=lambda *args:None).run("wait")
    assert r.status=="waiting"
