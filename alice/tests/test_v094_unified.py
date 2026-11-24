from alice.devices.unified import UnifiedDeviceAgent
class D:
    def discover(self,**k): return ["device"]
    def select(self,q): return q
class A:
    def request(self,d,s): return {"device_id":d,"scopes":list(s)}
    def approve(self,r): return {"approved":r}
class C:
    def connect(self,*a,**k): return "connected"
class Ctrl:
    def screenshot(self,*a): return "shot"
def test_unified_facade():
    u=UnifiedDeviceAgent(D(),A(),C(),Ctrl())
    assert u.find()==["device"]; assert u.select("phone")=="phone"
    assert u.authorize("id",["adb"])["device_id"]=="id"
    assert u.connect("id")=="connected"; assert u.screenshot("id","x")=="shot"
def test_approval_is_explicit():
    u=UnifiedDeviceAgent(D(),A(),C(),Ctrl())
    assert u.authorize("id",["adb"],approve=True)["approved"]=="id"
