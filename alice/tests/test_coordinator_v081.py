from alice.devices.registry import DeviceRegistry
from alice.devices.coordinator import DeviceCoordinator
class A:
 def ping(self): return 'pong'
def test_coordinator_requires_pairing(tmp_path):
 r=DeviceRegistry(tmp_path); d=r.register('phone','android',['ping']); c=DeviceCoordinator(r,{d['id']:A()})
 try:c.execute(d['id'],'ping'); assert False
 except PermissionError:pass
 r.pair(d['id']); assert c.execute(d['id'],'ping')=='pong'
