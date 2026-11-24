from __future__ import annotations
class CrossDeviceTaskExecutor:
    def __init__(self, agent): self.agent=agent
    def run(self, device_id, scope, operation, *args, **kwargs):
        # DeviceAgent remains the single permission gate.
        return self.agent.execute(device_id,scope,operation,*args,**kwargs)
    def run_many(self, steps):
        results=[]
        for step in steps:
            try:
                results.append({"id":step.get("id"),"ok":True,"result":self.run(step["device_id"],step["scope"],step["operation"],*step.get("args",[]),**step.get("kwargs",{}))})
            except Exception as e:
                results.append({"id":step.get("id"),"ok":False,"error":str(e)})
                break
        return results
