from __future__ import annotations
from dataclasses import dataclass, field
import time

@dataclass
class Connection:
    device_id: str
    transport: str
    endpoint: str
    connected: bool = False
    metadata: dict = field(default_factory=dict)

class AndroidConnectionManager:
    def __init__(self, registry, adb=None):
        self.registry, self.adb, self.connections = registry, adb, {}
    def connect(self, device_id, transport="adb", endpoint=None):
        d=self.registry.get(device_id)
        if not d: raise KeyError(device_id)
        if not d.get("paired"): raise PermissionError("device not authorized")
        endpoint=endpoint or device_id
        if transport=="adb":
            if self.adb is None: raise RuntimeError("ADB adapter required")
            if endpoint not in self.adb.devices(): raise ConnectionError("device not available")
        elif transport not in {"wifi","usb"}: raise ValueError("unsupported transport")
        c=Connection(device_id,transport,endpoint,True,{"connected_at":time.time()})
        self.connections[device_id]=c; self.registry.set_online(device_id,True)
        return c
    def disconnect(self, device_id):
        c=self.connections.pop(device_id,None)
        if c: c.connected=False
        if self.registry.get(device_id): self.registry.set_online(device_id,False)
        return c
    def get(self, device_id): return self.connections.get(device_id)
