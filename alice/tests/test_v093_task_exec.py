from alice.devices.task_exec import CrossDeviceTaskExecutor
class A:
    def execute(self,d,s,o,*a,**k): return o
def test_single(): assert CrossDeviceTaskExecutor(A()).run("d","read","ping")=="ping"
def test_stops_after_failure():
    class X:
        def __init__(self): self.n=0
        def execute(self,*a,**k):
            self.n+=1
            if self.n==2: raise RuntimeError("bad")
            return "ok"
    x=X(); out=CrossDeviceTaskExecutor(x).run_many([{"id":1,"device_id":"d","scope":"x","operation":"a"},{"id":2,"device_id":"d","scope":"x","operation":"b"},{"id":3,"device_id":"d","scope":"x","operation":"c"}])
    assert len(out)==2 and out[-1]["ok"] is False and x.n==2
