from alice.devices.registry import DeviceRegistry
from alice.devices.coordinator import DeviceCoordinator
from alice.security.device_consent import DeviceConsent
from alice.devices.agent import DeviceAgent
class A:
 def ping(self): return 'pong'
def test_device_agent_requires_explicit_scope(tmp_path):
 r=DeviceRegistry(tmp_path); d=r.register('phone','android',['ping']); r.pair(d['id']); c=DeviceCoordinator(r,{d['id']:A()}); s=DeviceConsent(tmp_path); a=DeviceAgent(c,s)
 try:a.execute(d['id'],'device_control','ping'); assert False
 except PermissionError:pass
 s.grant(d['id'],['device_control']); assert a.execute(d['id'],'device_control','ping')=='pong'
