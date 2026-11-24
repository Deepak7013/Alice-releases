from alice.devices.registry import DeviceRegistry
from alice.devices.connection import AndroidConnectionManager
from alice.devices.control import AndroidControl
class A:
    def devices(self): return ["abc"]
    def shell(self,d,c): self.last=(d,c); return "ok"
    def screenshot(self,d,p): return p
def setup(tmp_path):
    r=DeviceRegistry(tmp_path); r.register("Phone","android",["adb"],device_id="abc"); r.pair("abc")
    a=A(); m=AndroidConnectionManager(r,a); m.connect("abc"); return AndroidControl(a,m),a
def test_tap(tmp_path):
    c,a=setup(tmp_path); assert c.tap("abc",10,20)=="ok"; assert a.last[1]=="input tap 10 20"
def test_swipe(tmp_path):
    c,a=setup(tmp_path); c.swipe("abc",1,2,3,4,500); assert "input swipe 1 2 3 4 500" in a.last[1]
def test_text(tmp_path):
    c,a=setup(tmp_path); c.text("abc","hello world"); assert "input text hello%sworld" in a.last[1]
def test_unconnected_rejected(tmp_path):
    r=DeviceRegistry(tmp_path); r.register("Phone","android",["adb"],device_id="abc"); a=A()
    c=AndroidControl(a,AndroidConnectionManager(r,a))
    try:c.home("abc")
    except ConnectionError:pass
    else:assert False
