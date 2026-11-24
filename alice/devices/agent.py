from __future__ import annotations
class DeviceAgent:
    def __init__(self,coordinator,consent): self.coordinator=coordinator; self.consent=consent
    def inspect(self,device_id): return self.coordinator.registry.get(device_id)
    def execute(self,device_id,scope,operation,*args,**kwargs):
        if not self.consent.allowed(device_id,scope): raise PermissionError(f'consent required: {scope}')
        return self.coordinator.execute(device_id,operation,*args,**kwargs)
    def summarize_notifications(self,device_id,reader):
        if not self.consent.allowed(device_id,'notifications'): raise PermissionError('consent required: notifications')
        return reader.recent_notifications()
