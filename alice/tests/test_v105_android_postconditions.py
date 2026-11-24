from types import SimpleNamespace

from alice.android_intelligence.models import AndroidElement, AndroidScreenState
from alice.android_intelligence.postconditions import (
    capture_android_text_baseline,
    verify_android_launch_postcondition,
    verify_android_text_postcondition,
    tap_android_element_with_expected_transition,
    verify_android_tap_postcondition,
    press_android_key_with_expected_transition,
    swipe_android_with_expected_transition,
    type_android_text_with_baseline,
)
from alice.capabilities.manager import CapabilityManager
from alice.agent.executor import Executor
from alice.execution.postconditions import PostconditionRegistry
from alice.tools.registry import ToolRegistry


class Observer:
    def __init__(self, package="com.example.app", activity=".MainActivity", error=None):
        self.package = package
        self.activity = activity
        self.error = error
        self.serials = []

    def observe(self, serial):
        self.serials.append(serial)
        if self.error:
            raise self.error
        return SimpleNamespace(package=self.package, activity=self.activity)


def test_android_launch_verifier_requires_exact_foreground_package():
    observer = Observer()
    result = verify_android_launch_postcondition(
        observer,
        {"serial": "device-1", "package": "com.example.app"},
        {"ok": False},
    )

    assert result.ok is True
    assert result.evidence["observed"] is True
    assert result.evidence["package_matches"] is True
    assert "device-1" not in str(result.evidence)
    assert observer.serials == ["device-1"]


def test_android_launch_verifier_fails_for_different_foreground_package():
    result = verify_android_launch_postcondition(
        Observer(package="com.other.app"),
        {"serial": "device-1", "package": "com.example.app"},
        {"ok": True},
    )

    assert result.ok is False
    assert result.evidence["observed"] is True
    assert result.evidence["package_matches"] is False


def test_android_launch_verifier_fails_closed_on_missing_target_or_observer_error():
    missing = verify_android_launch_postcondition(Observer(), {"package": "com.example.app"}, {})
    failed = verify_android_launch_postcondition(
        Observer(error=RuntimeError("private adb detail")),
        {"serial": "device-1", "package": "com.example.app"},
        {"ok": True},
    )

    assert missing.ok is False and missing.evidence["observed"] is False
    assert failed.ok is False and failed.evidence["observed"] is False
    assert "private adb detail" not in str(failed)


def test_android_launch_tool_registers_success_only_after_foreground_readback(tmp_path):
    manager = CapabilityManager(tmp_path)
    tools = ToolRegistry(capability_manager=manager)
    tools.add("android_launch_app", "Launch an Android package", lambda **_args: {"ok": True}, "execute")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register(
        "android_launch_app",
        lambda args, result: verify_android_launch_postcondition(Observer(), args, result),
    )
    executor = Executor(tools, capabilities=manager)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "android_launch_app", "args": {
        "serial": "device-1", "package": "com.example.app",
    }}]})[0]

    assert result["status"] == "verified"
    assert manager.can_claim("android_launch_app")


def test_android_launch_tool_is_wired_to_the_live_ui_observer():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert "android_observer=AndroidIntelligenceController()" in source
    assert 't.postconditions.register("android_launch_app",lambda args,result:verify_android_launch_postcondition(android_observer,args,result))' in source
    assert '"android_launch_app","Launch a package on the specified Android serial and independently verify it is foreground",android_launch_app' in source


class EditableObserver:
    def __init__(self, value="old", field_id="com.example:id/message", focused=True):
        self.value = value
        self.field_id = field_id
        self.focused = focused
        self.reads = 0

    def observe(self, serial):
        self.reads += 1
        element = AndroidElement(
            text=self.value,
            resource_id=self.field_id,
            class_name="android.widget.EditText",
            bounds=(10, 20, 300, 90),
            focused=self.focused,
        )
        return AndroidScreenState(serial, "com.example.chat", ".ChatActivity", [element])


def test_whatsapp_placeholder_requires_independent_empty_composer_control():
    field = AndroidElement(text="Message", resource_id="com.whatsapp:id/entry",
        class_name="android.widget.EditText", focused=True)
    voice = AndroidElement(resource_id="com.whatsapp:id/voice_note_btn",
        class_name="android.widget.ImageButton", enabled=True)
    state = AndroidScreenState("device-1", "com.whatsapp", ".Conversation", [field, voice])

    class StateObserver:
        def observe(self, serial): return state
    baseline = capture_android_text_baseline(StateObserver(), "device-1")
    assert baseline["before_text"] == ""
    assert baseline["placeholder_only"] is True
    assert baseline["placeholder_signal"] == "whatsapp_voice_note_control"


def test_whatsapp_placeholder_without_empty_control_or_with_send_control_fails_closed():
    field = AndroidElement(text="Message", resource_id="com.whatsapp:id/entry",
        class_name="android.widget.EditText", focused=True)
    voice = AndroidElement(resource_id="com.whatsapp:id/voice_note_btn", enabled=True)

    class StateObserver:
        def __init__(self, elements, package="com.whatsapp"): self.state = AndroidScreenState("device-1", package, ".Conversation", elements)
        def observe(self, serial): return self.state

    without_voice = capture_android_text_baseline(StateObserver([field]), "device-1")
    with_send = capture_android_text_baseline(StateObserver([field, voice,
        AndroidElement(resource_id="com.whatsapp:id/send", enabled=True)]), "device-1")
    wrong_package = capture_android_text_baseline(StateObserver([field, voice], "com.example.chat"), "device-1")
    assert without_voice["placeholder_only"] is False
    assert with_send["placeholder_only"] is False
    assert wrong_package["placeholder_only"] is False
    assert without_voice["before_text"] == with_send["before_text"] == wrong_package["before_text"] == "Message"


def test_android_text_readback_keeps_field_identity_when_layout_bounds_change():
    class ResizingObserver:
        def __init__(self):
            self.state = AndroidScreenState("device-1", "com.whatsapp", ".Conversation", [
                AndroidElement(text="", resource_id="com.whatsapp:id/entry",
                    class_name="android.widget.EditText", focused=True, bounds=(10, 20, 300, 90)),
            ])
        def observe(self, serial): return self.state

    class ResizingController:
        def __init__(self, observer): self.observer = observer
        def text(self, value, serial):
            self.observer.state.elements = [AndroidElement(text=value,
                resource_id="com.whatsapp:id/entry", class_name="android.widget.EditText",
                focused=True, bounds=(10, 20, 800, 90))]
            return {"ok": True}

    observer = ResizingObserver()
    typed = type_android_text_with_baseline(ResizingController(observer), observer,
        "device-1", "probe", baseline=capture_android_text_baseline(observer, "device-1"))
    check = verify_android_text_postcondition(observer, {"serial": "device-1", "text": "probe"}, typed)
    assert check.ok is True
    assert check.evidence["same_field"] is True
    assert check.evidence["exact_append"] is True


class TypingController:
    def __init__(self, observer, *, redirect=False):
        self.observer = observer
        self.redirect = redirect
        self.calls = []

    def text(self, value, serial):
        self.calls.append((value, serial))
        if self.redirect:
            self.observer.field_id = "com.example:id/other"
        else:
            self.observer.value += value
        return {"ok": True}


def test_android_text_is_verified_by_exact_readback_in_same_focused_field(tmp_path):
    observer = EditableObserver("Draft: ")
    controller = TypingController(observer)
    manager = CapabilityManager(tmp_path)
    tools = ToolRegistry(capability_manager=manager)
    tools.add(
        "android_text", "Type and verify focused text",
        lambda serial, text: type_android_text_with_baseline(controller, observer, serial, text),
        "execute",
    )
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register(
        "android_text",
        lambda args, result: verify_android_text_postcondition(observer, args, result),
    )
    executor = Executor(tools, capabilities=manager)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "android_text", "args": {
        "serial": "device-1", "text": "hello world",
    }}]})[0]

    assert observer.reads == 2
    assert controller.calls == [("hello world", "device-1")]
    assert result["status"] == "verified"
    evidence = result["result"]["postcondition"]["evidence"]
    assert evidence["same_screen"] is True
    assert evidence["same_field"] is True
    assert evidence["exact_append"] is True
    assert "hello world" not in str(result)
    assert manager.can_claim("android_text")


def test_android_text_fails_before_mutation_without_one_focused_edit_field():
    observer = EditableObserver(focused=False)
    controller = TypingController(observer)

    try:
        type_android_text_with_baseline(controller, observer, "device-1", "hello")
    except ValueError as exc:
        assert "Focus exactly one identifiable" in str(exc)
    else:
        raise AssertionError("text entry proceeded without a focused editable field")

    assert controller.calls == []


def test_android_text_fails_when_focus_moves_to_a_different_field():
    observer = EditableObserver("Draft: ")
    controller = TypingController(observer, redirect=True)
    result = type_android_text_with_baseline(controller, observer, "device-1", "hello")

    check = verify_android_text_postcondition(
        observer, {"serial": "device-1", "text": "hello"}, result,
    )

    assert check.ok is False
    assert check.evidence["same_field"] is False
    assert check.evidence["exact_append"] is False


def test_android_text_supplied_baseline_is_bound_to_the_target_device():
    from alice.android_intelligence.postconditions import capture_android_text_baseline

    observer = EditableObserver("before")
    controller = TypingController(observer)
    baseline = capture_android_text_baseline(observer, "device-1")
    result = type_android_text_with_baseline(
        controller, observer, "device-1", "after", baseline=baseline,
    )
    assert result["ok"] is True
    assert controller.calls == [("after", "device-1")]

    try:
        type_android_text_with_baseline(
            controller, observer, "device-2", "must not type", baseline=baseline,
        )
    except ValueError as exc:
        assert "does not belong to the requested device" in str(exc)
    else:
        raise AssertionError("an Android text baseline from another device was accepted")

    assert len(controller.calls) == 1


def test_android_parser_keeps_empty_focused_edit_field_for_pre_action_baseline():
    from alice.android_intelligence.state import AndroidStateParser

    xml = '<hierarchy><node class="android.widget.EditText" resource-id="com.example:id/input" focused="true" text="" bounds="[10,20][300,90]"/></hierarchy>'
    state = AndroidStateParser().parse("device-1", xml, "com.example", ".Main")

    assert len(state.elements) == 1
    assert state.elements[0].focused is True
    assert state.elements[0].resource_id == "com.example:id/input"


def test_android_parser_preserves_explicit_edit_field_hint_separately_from_text():
    from alice.android_intelligence.state import AndroidStateParser

    xml = '<hierarchy><node class="android.widget.EditText" resource-id="com.whatsapp:id/entry" focused="true" text="Message" hint="Message" bounds="[10,20][300,90]"/></hierarchy>'
    state = AndroidStateParser().parse("device-1", xml, "com.whatsapp", ".Conversation")

    assert len(state.elements) == 1
    assert state.elements[0].text == "Message"
    assert state.elements[0].hint == "Message"


def test_android_text_postcondition_is_wired_to_the_active_tool():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert 't.postconditions.register("android_text",lambda args,result:verify_android_text_postcondition(android_observer,args,result))' in source
    assert '"android_text","Type into the uniquely focused Android edit field and verify the exact appended text",android_text' in source


def test_whatsapp_send_uses_verified_composer_instead_of_direct_unobserved_text():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert "wa_composer=VerifiedWhatsAppComposer(wa_control,android_observer,wa_observer)" in source
    assert "return wa_composer.prepare(device_id,chat,value)" in source
    assert "android_text_command(value)" in source


def test_android_tap_is_verified_by_new_accessibility_state_and_executor(tmp_path):
    class TapObserver:
        def __init__(self):
            self.state=AndroidScreenState("device-1","com.example.app",".Main",[
                AndroidElement(text="Open settings",resource_id="com.example:id/open",
                    clickable=True,enabled=True,bounds=(10,20,210,80)),
            ])
        def observe(self,serial):
            assert serial==self.state.serial
            return self.state

    class TapController:
        def __init__(self,observer): self.observer=observer; self.calls=[]
        def click(self,serial,element):
            self.calls.append((serial,element))
            self.observer.state=AndroidScreenState(serial,"com.example.app",".Settings",[
                AndroidElement(text="Settings opened",resource_id="com.example:id/title"),
            ])
            return SimpleNamespace(ok=True)

    observer=TapObserver();controller=TapController(observer)
    tools=ToolRegistry();tools.postconditions=PostconditionRegistry()
    def tap(serial,target_text,expected_text=None,expected_package=None):
        return tap_android_element_with_expected_transition(controller,observer,serial,target_text,
            expected_text=expected_text,expected_package=expected_package)
    tools.add("android_tap","Tap visible element and verify result",tap,"execute")
    tools.postconditions.register("android_tap",lambda args,result:
        verify_android_tap_postcondition(observer,args,result))
    executor=Executor(tools);executor.permissions.needs_confirmation=lambda _name,_args:False
    result=executor.run({"steps":[{"tool":"android_tap","args":{
        "serial":"device-1","target_text":"Open settings","expected_text":"Settings opened"}}]})[0]

    assert result["status"]=="verified"
    assert len(controller.calls)==1
    assert "_postcondition_context" not in result["result"]
    evidence=result["result"]["postcondition"]["evidence"]
    assert evidence["observed"] is True and evidence["expected_text_visible"] is True
    assert "Open settings" not in repr(evidence)
    assert "device-1" not in repr(evidence)


def test_android_tap_fails_before_mutation_for_ambiguous_or_nontransitioning_requests():
    class TapObserver:
        def __init__(self,elements):
            self.state=AndroidScreenState("device-1","com.example.app",".Main",elements)
        def observe(self,serial):return self.state

    class TapController:
        def __init__(self):self.calls=[]
        def click(self,*args):self.calls.append(args);return SimpleNamespace(ok=True)

    element=AndroidElement(text="Open settings",clickable=True,bounds=(1,2,30,40))
    controller=TapController();observer=TapObserver([element,element])
    try:
        tap_android_element_with_expected_transition(controller,observer,"device-1","Open settings",
            expected_text="Settings opened")
    except ValueError as exc:assert "unique" in str(exc)
    else:raise AssertionError("ambiguous Android target was accepted")
    assert controller.calls==[]

    observer=TapObserver([element,AndroidElement(text="Already open")])
    try:
        tap_android_element_with_expected_transition(controller,observer,"device-1","Open settings",
            expected_text="Already open")
    except ValueError as exc:assert "visible before the tap" in str(exc)
    else:raise AssertionError("pre-existing expected state was accepted")
    assert controller.calls==[]

    try:
        tap_android_element_with_expected_transition(controller,observer,"device-1","Open settings")
    except ValueError as exc:assert "exactly one expected result" in str(exc)
    else:raise AssertionError("tap without a postcondition was accepted")
    assert controller.calls==[]


def test_android_tap_tool_is_wired_to_semantic_observer_postcondition():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text(encoding="utf-8")
    assert 't.postconditions.register("android_tap",lambda args,result:verify_android_tap_postcondition(android_observer,args,result))' in source
    assert '"android_tap","Tap one uniquely observed Android control and verify an expected UI transition",android_tap' in source


def test_android_keyevent_and_swipe_require_observed_transitions():
    class TransitionObserver:
        def __init__(self):
            self.state=AndroidScreenState("device-1","com.example.app",".Main",[
                AndroidElement(text="Search",class_name="android.widget.EditText",focused=True,enabled=True),
            ])
        def observe(self,serial):
            assert serial==self.state.serial
            return self.state

    class TransitionController:
        def __init__(self,observer):self.observer=observer;self.calls=[]
        def press(self,serial,key):
            self.calls.append(("keyevent",serial,key))
            self.observer.state=AndroidScreenState(serial,"com.example.app",".Results",[
                AndroidElement(text="Search results loaded"),
            ])
            return SimpleNamespace(ok=True)
        def swipe(self,serial,x1,y1,x2,y2,duration_ms):
            self.calls.append(("swipe",serial,x1,y1,x2,y2,duration_ms))
            self.observer.state=AndroidScreenState(serial,"com.example.app",".List",[
                AndroidElement(text="More results visible"),
            ])
            return SimpleNamespace(ok=True)

    observer=TransitionObserver();controller=TransitionController(observer)
    key_result=press_android_key_with_expected_transition(controller,observer,"device-1","ENTER",
        expected_text="Search results loaded")
    assert verify_android_tap_postcondition(observer,{
        "serial":"device-1","key":"ENTER","expected_text":"Search results loaded"},key_result).ok
    assert controller.calls==[("keyevent","device-1","ENTER")]

    observer.state=AndroidScreenState("device-1","com.example.app",".List",[
        AndroidElement(text="Top of list"),
    ])
    swipe_result=swipe_android_with_expected_transition(controller,observer,"device-1",1,2,3,4,400,
        expected_text="More results visible")
    assert verify_android_tap_postcondition(observer,{
        "serial":"device-1","x1":1,"y1":2,"x2":3,"y2":4,"duration_ms":400,
        "expected_text":"More results visible"},swipe_result).ok
    assert controller.calls[-1]==("swipe","device-1",1,2,3,4,400)

    try:
        press_android_key_with_expected_transition(controller,observer,"device-1","UNKNOWN",
            expected_text="anything")
    except ValueError as exc:assert "allowlist" in str(exc)
    else:raise AssertionError("unknown Android key event was accepted")

    try:
        swipe_android_with_expected_transition(controller,observer,"device-1",1,2,3,4,5,
            expected_text="anything")
    except ValueError as exc:assert "duration" in str(exc)
    else:raise AssertionError("out-of-range Android swipe was accepted")


def test_android_swipe_and_keyevent_are_registered_with_observers():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text(encoding="utf-8")
    assert 't.postconditions.register("android_swipe",lambda args,result:verify_android_tap_postcondition(android_observer,args,result))' in source
    assert 't.postconditions.register("android_keyevent",lambda args,result:verify_android_tap_postcondition(android_observer,args,result))' in source
