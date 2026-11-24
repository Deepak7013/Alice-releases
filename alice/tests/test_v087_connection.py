from alice.devices.registry import DeviceRegistry
from alice.devices.connection import AndroidConnectionManager
class FakeADB:
    def devices(self): return ["abc"]
def test_connect_requires_authorization(tmp_path):
    r=DeviceRegistry(tmp_path); d=r.register("Phone","android",["adb"],device_id="abc")
    m=AndroidConnectionManager(r,FakeADB())
    try: m.connect("abc")
    except PermissionError: pass
    else: assert False
def test_connect_authorized(tmp_path):
    r=DeviceRegistry(tmp_path); d=r.register("Phone","android",["adb"],device_id="abc"); r.pair("abc")
    c=AndroidConnectionManager(r,FakeADB()).connect("abc")
    assert c.connected and c.endpoint=="abc"
def test_disconnect_updates_registry(tmp_path):
    r=DeviceRegistry(tmp_path); r.register("Phone","android",["adb"],device_id="abc"); r.pair("abc")
    m=AndroidConnectionManager(r,FakeADB()); m.connect("abc"); m.disconnect("abc")
    assert r.get("abc")["online"] is False
def test_unknown_transport_rejected(tmp_path):
    r=DeviceRegistry(tmp_path); r.register("Phone","android",device_id="abc"); r.pair("abc")
    try: AndroidConnectionManager(r,FakeADB()).connect("abc","bluetooth")
    except ValueError: pass
    else: assert False
