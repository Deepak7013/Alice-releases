from alice.messaging.whatsapp_interface import WhatsAppInterface
from alice.messaging.whatsapp import AndroidWhatsAppUIObserver, VisibleChatDeliveryVerifier, VerifiedWhatsAppComposer, WhatsAppAccessError
class C:
    def __init__(self): self.adb=self
    def _target(self,d): return d
    def open(self,d): return "opened"
    def text(self,d,t): self.last=t; return "typed"
    def prepare_message(self,d,chat,text): self.last=text; return {"ok":True,"verified":True}
    def shell(self,d,c): self.cmd=c; return "sent"
    def launch(self,d,p): self.pkg=p; return "opened"
class N:
    def list(self,package=None): return [{"package":package}]
class Consent:
    def __init__(self,s): self.s=set(s)
    def allowed(self,d,s): return s in self.s
def test_read_scope():
    w=WhatsAppInterface(C(),N(),Consent(["messages.read"])); assert w.recent("x")[0]["package"]=="com.whatsapp"
def test_send_requires_send_scope():
    w=WhatsAppInterface(C(),N(),Consent(["messages.draft"]))
    try:w.send_reply("x","hi")
    except PermissionError:pass
    else:assert False

def test_android_text_command_quotes_shell_metacharacters_and_escapes_adb_text_tokens():
    import shlex
    from alice.messaging.whatsapp_interface import android_text_command

    command=android_text_command("hello; touch /tmp/nope & 100% 'quoted'")
    argv=shlex.split(command)
    assert argv[0:2]==["input","text"]
    assert argv[2]=="hello%3B%stouch%s/tmp/nope%s%26%s100%25%s'quoted'"
    assert len(argv)==3
def test_draft_is_not_send():
    c=C(); w=WhatsAppInterface(c,N(),Consent(["messages.draft","messages.open"]))
    w.draft_reply("x","hi"); assert not hasattr(c,"cmd")
def test_send_scope_sends():
    c=C(); w=WhatsAppInterface(c,N(),Consent(["messages.send","messages.open"]))
    result=w.send_reply("x","hi")
    assert not hasattr(c,"cmd") and not hasattr(c,"last")
    assert result["status"]=="not_sent"
    assert result["verified"] is False
    assert result["verification_reason"]=="chat_or_receipt_observer_unavailable"

def test_successful_command_is_not_delivery_verification():
    c=C(); w=WhatsAppInterface(c,N(),Consent(["messages.send","messages.open"]))
    result=w.send_reply("x","hi")
    assert not hasattr(c,"cmd")
    assert result["verified"] is False

def test_delivery_requires_observation_of_expected_chat_and_outgoing_content():
    class UI:
        def __init__(self): self.reads=0
        def read_visible_chat(self,device,chat):
            self.reads+=1
            if self.reads==1:
                return {"chat":chat,"messages":[{"id":"old","direction":"outgoing","text":"private message"}]}
            return {"chat":chat,"messages":[{"id":"old","direction":"outgoing","text":"private message"},
                {"id":"m-17","direction":"outgoing","text":"private message"}]}
    ui=UI(); verifier=VisibleChatDeliveryVerifier(ui)
    c=C(); w=WhatsAppInterface(c,N(),Consent(["messages.send","messages.open"]),verifier)
    result=w.send_reply("phone","private message",chat="Alice")
    assert ui.reads==2
    assert result["status"]=="verified" and result["verified"] is True
    assert result["evidence"]=={"observed":True,"conversation_matches":True,
        "outgoing":True,"content_matches":True,"newly_observed":True,"message_id":"m-17"}
    assert "private message" not in str(result)

def test_whatsapp_send_executor_claims_success_only_after_second_independent_ui_readback(tmp_path):
    from alice.agent.executor import Executor
    from alice.capabilities.manager import CapabilityManager
    from alice.execution.postconditions import PostconditionRegistry
    from alice.messaging.whatsapp import verify_whatsapp_send_postcondition
    from alice.tools.registry import ToolRegistry

    class UI:
        def __init__(self): self.reads=0
        def read_visible_chat(self,device,chat):
            self.reads+=1
            messages=[{"id":"old","direction":"outgoing","text":"older"}]
            if self.reads>=2:
                messages.append({"id":"new-1","direction":"outgoing","text":"hello"})
            return {"chat":chat,"messages":messages}

    ui=UI(); verifier=VisibleChatDeliveryVerifier(ui)
    interface=WhatsAppInterface(C(),N(),Consent(["messages.send"]),verifier)
    capabilities=CapabilityManager(tmp_path)
    tools=ToolRegistry(capability_manager=capabilities)
    tools.add("whatsapp_send_reply","Send verified reply",
        lambda device_id,chat,text:interface.send_reply(device_id,text,chat=chat),"external")
    tools.postconditions=PostconditionRegistry()
    tools.postconditions.register("whatsapp_send_reply",
        lambda args,result:verify_whatsapp_send_postcondition(verifier,args,result))
    executor=Executor(tools,capabilities=capabilities)
    executor.permissions.needs_confirmation=lambda _name,_args:False

    result=executor.run({"steps":[{"tool":"whatsapp_send_reply","args":{
        "device_id":"phone","chat":"Alice","text":"hello",
    }}]})[0]

    assert result["status"]=="verified"
    assert result["postcondition"]["ok"] is True
    assert ui.reads==3
    assert "hello" not in str(result)

def test_incomplete_observation_keeps_delivery_unverified():
    class Verifier:
        def snapshot(self,device,chat): return frozenset()
        def verify(self,device,chat,text,baseline):
            return {"observed":True,"conversation_matches":True,"outgoing":True,
                    "content_matches":False,"newly_observed":True}
    c=C(); w=WhatsAppInterface(c,N(),Consent(["messages.send","messages.open"]),Verifier())
    result=w.send_reply("phone","hi",chat="Alice")
    assert result["status"]=="attempted" and result["verified"] is False

def test_observer_failure_keeps_delivery_unverified():
    class Broken:
        def snapshot(self,device,chat): return frozenset()
        def verify(self,device,chat,text,baseline): raise RuntimeError("observer unavailable")
    c=C(); w=WhatsAppInterface(c,N(),Consent(["messages.send","messages.open"]),Broken())
    result=w.send_reply("phone","hi",chat="Alice")
    assert result["status"]=="attempted" and result["verified"] is False
    assert result["verification_reason"]=="receipt_observer_failed"

def test_message_send_refuses_legacy_unverified_text_path():
    class LegacyControl(C):
        prepare_message=None
    class Receipt:
        def snapshot(self,device,chat): return frozenset()
        def verify(self,*args): raise AssertionError("send verifier must not run")
    c=LegacyControl(); w=WhatsAppInterface(c,N(),Consent(["messages.send"]),Receipt())
    result=w.send_reply("phone","hi",chat="Alice")
    assert result["status"]=="not_sent"
    assert result["verification_reason"]=="verified_message_composer_unavailable"
    assert not hasattr(c,"cmd") and not hasattr(c,"last")

def test_message_send_does_not_press_enter_when_composition_readback_fails():
    class Unverified(C):
        def prepare_message(self,d,chat,text):
            self.last=text
            return {"ok":False,"verified":False,"draft_may_remain":True,
                    "verification_reason":"composer_text_readback_failed"}
    class Receipt:
        def snapshot(self,device,chat): return frozenset()
        def verify(self,*args): raise AssertionError("send verifier must not run")
    c=Unverified(); w=WhatsAppInterface(c,N(),Consent(["messages.send"]),Receipt())
    result=w.send_reply("phone","hi",chat="Alice")
    assert result["status"]=="not_sent"
    assert result["draft_may_remain"] is True
    assert not hasattr(c,"cmd")

def test_verified_composer_checks_whatsapp_focused_field_and_exact_append():
    from alice.android_intelligence.models import AndroidElement, AndroidScreenState
    class Screen:
        def __init__(self): self.value=""; self.package="com.whatsapp"; self.activity=".Conversation"; self.reads=0
        def observe(self,serial):
            self.reads+=1
            return AndroidScreenState(serial,self.package,self.activity,[
                AndroidElement(text="Alice",resource_id="com.whatsapp:id/conversation_contact_name"),
                AndroidElement(text=self.value,resource_id="com.whatsapp:id/composer",
                    class_name="android.widget.EditText",bounds=(10,20,300,90),focused=True),
            ])
    class Controller:
        def __init__(self,screen): self.screen=screen; self.calls=[]
        def text(self,text,serial): self.calls.append((text,serial)); self.screen.value+=text; return {"ok":True}
    class Chat:
        def __init__(self): self.reads=0
        def read_visible_chat(self,device,chat):
            self.reads+=1
            return {"chat":"Alice","messages":[]}
    screen=Screen(); controller=Controller(screen); chat=Chat()
    composer=VerifiedWhatsAppComposer(controller,screen,chat)
    result=composer.prepare("phone","Alice","hello")
    assert result["verified"] is True
    assert result["evidence"]["requested_chat_confirmed_before_and_after"] is True
    assert result["evidence"]["focused_composer_in_whatsapp"] is True
    assert result["evidence"]["composer_text_readback"]["exact_append"] is True
    assert chat.reads==2 and screen.reads==3
    assert controller.calls==[("hello","phone")]
    assert "hello" not in str(result)

def test_verified_composer_fails_before_typing_without_whatsapp_focus_or_unique_edit_field():
    from alice.android_intelligence.models import AndroidElement, AndroidScreenState
    class Screen:
        def __init__(self,package="com.android.settings",focused=False): self.package=package; self.focused=focused
        def observe(self,serial):
            return AndroidScreenState(serial,self.package,".Main",[
                AndroidElement(resource_id="other:id/input",class_name="android.widget.EditText",
                    bounds=(1,2,30,40),focused=self.focused),
            ])
    class Controller:
        calls=[]
        def text(self,*args): self.calls.append(args); return {"ok":True}
    class Chat:
        def read_visible_chat(self,device,chat): return {"chat":chat,"messages":[]}
    controller=Controller(); composer=VerifiedWhatsAppComposer(controller,Screen(),Chat())
    result=composer.prepare("phone","Alice","hello")
    assert result["verified"] is False
    assert result["verification_reason"]=="focused_composer_not_in_whatsapp"
    assert controller.calls==[]

    screen=Screen(package="com.whatsapp",focused=False)
    result=VerifiedWhatsAppComposer(controller,screen,Chat()).prepare("phone","Alice","hello")
    assert result["verified"] is False
    assert result["verification_reason"].startswith("focused_composer_observation_failed")
    assert controller.calls==[]

def test_wrong_visible_chat_is_rejected_before_typing_or_sending():
    class WrongChat:
        def snapshot(self,device,chat): return None
        def verify(self,*args): raise AssertionError("postcondition must not run")
    c=C(); w=WhatsAppInterface(c,N(),Consent(["messages.send"]),WrongChat())
    result=w.send_reply("phone","hi",chat="Alice")
    assert result["status"]=="not_sent"
    assert result["verification_reason"]=="requested_chat_not_confirmed_before_send"
    assert not hasattr(c,"last") and not hasattr(c,"cmd")

def test_android_observer_requires_whatsapp_and_exact_visible_chat():
    from alice.android_intelligence.models import AndroidElement, AndroidScreenState
    class Controller:
        def __init__(self,package="com.whatsapp"):
            self.state=AndroidScreenState("phone",package,".Conversation",[
                AndroidElement(text="Alice",resource_id="com.whatsapp:id/conversation_contact_name"),
                AndroidElement(content_desc="You: hello",resource_id="com.whatsapp:id/message_text",
                               class_name="android.widget.TextView",bounds=(600,500,1000,560)),
                AndroidElement(text="hello",resource_id="com.whatsapp:id/message_text",
                               class_name="android.widget.TextView",bounds=(20,500,400,560)),
            ])
        def observe(self,serial): return self.state
    observer=AndroidWhatsAppUIObserver(Controller())
    view=observer.read_visible_chat("phone","Alice")
    assert view["chat"]=="Alice"
    assert len(view["messages"])==1
    assert view["messages"][0]["direction"]=="outgoing"
    assert view["messages"][0]["text"]=="hello"
    try: observer.read_visible_chat("phone","Bob")
    except WhatsAppAccessError: pass
    else: assert False
    try: AndroidWhatsAppUIObserver(Controller("com.android.settings")).read_visible_chat("phone","Alice")
    except WhatsAppAccessError: pass
    else: assert False
