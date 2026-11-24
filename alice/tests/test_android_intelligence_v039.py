from alice.android_intelligence import AndroidStateParser, AndroidOrchestrator

XML = '''<hierarchy><node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]"><node text="Settings" content-desc="Settings" resource-id="com.demo:id/settings" class="android.widget.Button" clickable="true" enabled="true" bounds="[40,100][400,220]"/><node text="Disabled" class="android.widget.Button" clickable="true" enabled="false" bounds="[40,300][400,420]"/></node></hierarchy>'''

class P:
    returncode=0
    stdout=""
    stderr=""

class FakeController:
    def __init__(self): self.clicks=[]; self.n=0
    def observe(self, serial):
        from alice.android_intelligence.models import AndroidScreenState
        self.n += 1
        return AndroidScreenState(serial, "com.demo", ".Main", AndroidStateParser().parse(serial, XML).elements, str(self.n))
    def click(self, serial, element):
        from alice.android_intelligence.models import AndroidActionResult
        self.clicks.append(element.label)
        return AndroidActionResult(True, "click")
    def launch(self, serial, package):
        from alice.android_intelligence.models import AndroidActionResult
        return AndroidActionResult(True, "launch")
    def press(self, serial, key):
        from alice.android_intelligence.models import AndroidActionResult
        return AndroidActionResult(True, "keyevent")

def test_parser_extracts_semantic_elements():
    state = AndroidStateParser().parse("ABC", XML, "com.demo", ".Main")
    assert state.find("Settings", "button").resource_id == "com.demo:id/settings"
    assert state.find("Disabled") is not None

def test_semantic_session_clicks_named_element():
    c=FakeController(); s=AndroidOrchestrator(c).session("ABC")
    r=s.click("Settings", "button")
    assert r.ok and c.clicks == ["Settings"]

def test_disabled_element_is_rejected():
    c=FakeController(); s=AndroidOrchestrator(c).session("ABC")
    r=s.click("Disabled", "button")
    assert not r.ok

def test_orchestrator_runs_and_verifies():
    c=FakeController(); o=AndroidOrchestrator(c)
    r=o.run("ABC", "open settings", lambda g,before,steps:{"name":"click","query":"Settings","role":"button"}, verifier=lambda g,b,a,x: True)
    assert r.status == "completed" and r.steps

class Runner:
    def __init__(self): self.calls=[]
    def __call__(self, args, timeout=30):
        self.calls.append(list(args))
        class R:
            returncode=0; stderr=""; stdout=""
        r=R()
        if args[:2] == ["devices", "-l"]:
            r.stdout="List of devices attached\nABC123\tdevice product:demo model:Pixel_8\n"
        elif "dumpsys" in args:
            r.stdout="mResumedActivity: ActivityRecord{ x com.demo/.MainActivity t1}"
        elif "uiautomator" in args:
            r.stdout=XML
        return r

def test_controller_discovers_device_and_observes():
    from alice.android_intelligence import AndroidIntelligenceController
    r=Runner(); c=AndroidIntelligenceController(runner=r)
    devices=c.devices()
    assert devices[0].serial == "ABC123" and devices[0].model == "Pixel_8"
    state=c.observe("ABC123")
    assert state.package == "com.demo" and state.find("Settings") is not None

def test_controller_rejects_unsafe_key():
    from alice.android_intelligence import AndroidIntelligenceController
    c=AndroidIntelligenceController(runner=Runner())
    try: c.press("ABC123", "DELETE_ALL")
    except ValueError: pass
    else: assert False
