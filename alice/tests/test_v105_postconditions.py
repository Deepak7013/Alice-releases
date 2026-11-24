from alice.agent.executor import Executor as AgentExecutor
from alice.capabilities.manager import CapabilityManager
from alice.execution.postconditions import PostconditionRegistry, PostconditionResult
from alice.messaging.whatsapp import VisibleChatDeliveryVerifier, verify_whatsapp_send_postcondition
from alice.messaging.whatsapp_interface import WhatsAppInterface
from alice.tools.registry import ToolRegistry


class Consent:
    def allowed(self, device_id, scope):
        return device_id == "phone-1" and scope == "messages.send"


class ADB:
    def shell(self, device_id, command):
        return {"device": device_id, "command_accepted": True}


class Control:
    adb = ADB()

    def _target(self, device_id):
        return device_id

    def text(self, device_id, value):
        return {"typed": True, "device": device_id}

    def prepare_message(self, device_id, chat, value):
        # This fixture isolates the delivery-receipt verifier. The real
        # VerifiedWhatsAppComposer safety behavior is covered separately.
        return {"ok": True, "verified": True}


class ScriptedVisibleUI:
    def __init__(self, after_send):
        self.after_send = after_send
        self.read_count = 0

    def read_visible_chat(self, device_id, chat):
        self.read_count += 1
        if self.read_count == 1:
            messages = [{"id": "old", "direction": "outgoing", "text": "prior message"}]
        elif self.read_count == 2:
            messages = [
                {"id": "old", "direction": "outgoing", "text": "prior message"},
                {"id": "new-1", "direction": "outgoing", "text": "hello"},
            ]
        else:
            messages = self.after_send
        return {"chat": "Alice", "messages": messages}


def _run_send(tmp_path, final_messages):
    manager = CapabilityManager(tmp_path)
    tools = ToolRegistry(capability_manager=manager)
    ui = ScriptedVisibleUI(final_messages)
    delivery_verifier = VisibleChatDeliveryVerifier(ui)
    interface = WhatsAppInterface(Control(), None, Consent(), delivery_verifier)
    tools.add(
        "whatsapp_send_reply",
        "Send a scoped message and verify its visible delivery",
        lambda **args: interface.send_reply(args["device_id"], args["text"], chat=args["chat"]),
        "external",
    )
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register(
        "whatsapp_send_reply",
        lambda args, result: verify_whatsapp_send_postcondition(delivery_verifier, args, result),
    )
    executor = AgentExecutor(tools, capabilities=manager)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    result = executor.run({"steps": [{
        "tool": "whatsapp_send_reply",
        "args": {"device_id": "phone-1", "chat": "Alice", "text": "hello"},
    }]})[0]
    return result, manager, ui


def test_whatsapp_send_is_verified_by_a_second_visible_ui_observation(tmp_path):
    visible = [
        {"id": "old", "direction": "outgoing", "text": "prior message"},
        {"id": "new-1", "direction": "outgoing", "text": "hello"},
    ]

    result, manager, ui = _run_send(tmp_path, visible)

    assert ui.read_count == 3  # pre-send baseline, interface check, executor postcondition
    assert result["status"] == "verified"
    assert result["result"]["postcondition"]["evidence"] == {
        "observed": True,
        "conversation_matches": True,
        "outgoing": True,
        "content_matches": True,
        "newly_observed": True,
        "message_id": "new-1",
    }
    assert "_postcondition_context" not in result["result"]
    assert manager.can_claim("whatsapp_send_reply")


def test_whatsapp_self_report_does_not_override_failed_second_observation(tmp_path):
    no_new_message = [{"id": "old", "direction": "outgoing", "text": "prior message"}]

    result, manager, ui = _run_send(tmp_path, no_new_message)

    assert ui.read_count == 3
    assert result["status"] == "attempted"
    assert result["verified"] is False
    assert result["result"]["tool_reported_verified"] is True
    assert result["result"]["verified"] is False
    assert result["result"]["postcondition"]["ok"] is False
    capability = manager.get("whatsapp_send_reply")
    assert capability["success_count"] == 0
    assert capability["failure_count"] == 1
    assert capability["verified"] is False


def test_postcondition_exception_fails_closed_without_leaking_exception_text(tmp_path):
    tools = ToolRegistry()
    tools.add("mutate", "Mutate state", lambda: {"verified": True, "evidence": {"claimed": True}}, "execute")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register("mutate", lambda _args, _result: (_ for _ in ()).throw(RuntimeError("private detail")))
    executor = AgentExecutor(tools)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "mutate", "args": {}}]})[0]

    assert result["status"] == "attempted"
    assert result["result"]["postcondition"]["reason"] == "verifier_error:RuntimeError"
    assert "private detail" not in str(result)


def test_registry_rejects_unstructured_success_evidence():
    registry = PostconditionRegistry()
    registry.register("mutate", lambda _args, _result: PostconditionResult(True, {"changed": True}, "claimed"))

    result = registry.verify("mutate", {}, {"verified": True})

    assert result.ok is False
    assert result.evidence == {"observed": False}
    assert result.reason == "verified_result_requires_observed_evidence"


def test_workspace_write_requires_disk_readback_before_success(tmp_path, monkeypatch):
    from alice.workspace import files
    from alice.workspace.postconditions import verify_workspace_file_write_postcondition

    monkeypatch.setattr(files, "ROOT", tmp_path.resolve())
    tools = ToolRegistry()
    tools.add("write_file", "Write a workspace file", files.write_file, "write")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register("write_file", verify_workspace_file_write_postcondition)
    executor = AgentExecutor(tools)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "write_file", "args": {
        "path": "notes/verified.txt", "content": "persisted value",
    }}]})[0]

    assert result["status"] == "verified"
    assert result["postcondition"]["evidence"]["observed"] is True
    assert result["postcondition"]["evidence"]["content_matches"] is True
    assert (tmp_path / "notes" / "verified.txt").read_text(encoding="utf-8") == "persisted value"


def test_workspace_write_mismatch_stays_attempted(tmp_path, monkeypatch):
    from alice.workspace import files
    from alice.workspace.postconditions import verify_workspace_file_write_postcondition

    monkeypatch.setattr(files, "ROOT", tmp_path.resolve())

    def write_wrong_value(path, content):
        target = files.safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("different value", encoding="utf-8")
        return str(target.relative_to(files.ROOT))

    tools = ToolRegistry()
    tools.add("write_file", "Write a workspace file", write_wrong_value, "write")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register("write_file", verify_workspace_file_write_postcondition)
    executor = AgentExecutor(tools)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "write_file", "args": {
        "path": "notes/verified.txt", "content": "expected value",
    }}]})[0]

    assert result["status"] == "attempted"
    assert result["verified"] is False
    assert result["postcondition"]["ok"] is False
