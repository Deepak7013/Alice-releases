from __future__ import annotations
class UnifiedDeviceAgent:
    def __init__(self, discovery, authorizer, connections, control, messenger=None, files=None, tasks=None):
        self.discovery=discovery; self.authorizer=authorizer; self.connections=connections
        self.control=control; self.messenger=messenger; self.files=files; self.tasks=tasks
    def find(self, query=None): return self.discovery.discover(query=query)
    def select(self, query): return self.discovery.select(query)
    def authorize(self, device_id, scopes, approve=False): return self.authorizer.approve(device_id) if approve else self.authorizer.request(device_id,scopes)
    def connect(self, device_id, transport="adb", endpoint=None): return self.connections.connect(device_id,transport,endpoint)
    def screenshot(self, device_id, path): return self.control.screenshot(device_id,path)
