from __future__ import annotations
class DeviceCoordinator:
    def __init__(self,registry,adapters=None): self.registry=registry; self.adapters=adapters or {}
    def capabilities(self,capability): return self.registry.find_capability(capability)
    def adapter_for(self,device_id):
        d=self.registry.get(device_id)
        if not d or not d.get('paired'): raise PermissionError('device not paired')
        if device_id not in self.adapters: raise LookupError('no adapter for device')
        return self.adapters[device_id]
    def execute(self,device_id,operation,*args,**kwargs): return getattr(self.adapter_for(device_id),operation)(*args,**kwargs)
