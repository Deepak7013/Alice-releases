import pytest

from alice.capabilities.manager import CapabilityManager, STATUS_UNVERIFIED
from alice.actions.engine import ActionEngine
from alice.actions.store import ActionStore
from alice.agent.executor import Executor as AgentExecutor
from alice.execution.postconditions import PostconditionRegistry, PostconditionResult
from alice.execution.verify_loop import Verification, VerifiedExecutor
from alice.tools.registry import ToolRegistry


def test_runtime_tool_is_registered_with_capability_and_risk_scope(tmp_path):
    manager = CapabilityManager(tmp_path)
    tools = ToolRegistry(capability_manager=manager)
    tools.add("send_message", "Send a message", lambda text: {"status": "attempted"}, "external")

    capability = manager.get("send_message")
    assert capability["kind"] == "runtime_tool"
    assert capability["source"] == "tool_registry"
    assert capability["permissions"] == ["external"]
    assert capability["status"] == STATUS_UNVERIFIED
    assert capability["verified"] is False
    assert CapabilityManager(tmp_path).get("send_message")["permissions"] == ["external"]

    live = tools.inventory()[0]
    assert live["name"] == "send_message"
    assert live["risk"] == "external"
    assert live["capability"]["status"] == STATUS_UNVERIFIED
    assert live["capability"]["verified"] is False


def test_tool_return_value_does_not_claim_verified_capability(tmp_path):
    manager = CapabilityManager(tmp_path)
    tools = ToolRegistry(capability_manager=manager)
    tools.add("write_file", "Write a file", lambda: {"ok": True, "verified": True}, "write")

    result = tools.run("write_file")

    assert result["verified"] is True
    assert manager.get("write_file")["verified"] is False
    assert manager.get("write_file")["status"] == STATUS_UNVERIFIED


def test_runtime_tool_registration_preserves_existing_verification(tmp_path):
    manager = CapabilityManager(tmp_path)
    manager.register("browser_snapshot", "Existing capability")
    manager.record_success("browser_snapshot", note="verified by a separate acceptance check")
    tools = ToolRegistry(capability_manager=manager)
    tools.add("browser_snapshot", "Inspect browser state", lambda: {}, "read")

    capability = manager.get("browser_snapshot")
    assert capability["verified"] is True
    assert capability["status"] == "available"


def test_ui_runtime_registry_uses_persistent_capability_manager():
    from pathlib import Path

    app_source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    assert "ToolRegistry(capability_manager=self.capabilities)" in app_source
    assert "wa_observer=AndroidWhatsAppUIObserver(android_observer)" in app_source
    assert 't.add("whatsapp_visible_chat"' in app_source
    assert 't.add("whatsapp_send_reply"' in app_source
    assert "t.postconditions=PostconditionRegistry()" in app_source
    assert 't.postconditions.register(\n            "whatsapp_send_reply"' in app_source
    assert 't.postconditions.register("write_file"' in app_source
    assert 't.postconditions.register("device_graph_link"' in app_source
    assert 't.add("device_graph_snapshot"' in app_source
    assert 't.add("device_graph_link"' in app_source
    assert 't.add("devour_multiple_repositories"' in app_source
    assert 't.postconditions.register("devour_multiple_repositories", self.devour.verify_multi_postcondition)' in app_source
    assert 't.postconditions.register("browser_open",lambda args,result:verify_browser_open_postcondition(browser,args,result))' in app_source
    assert 't.postconditions.register("browser_new_tab",lambda args,result:verify_browser_new_tab_postcondition(browser,args,result))' in app_source
    assert 't.postconditions.register("browser_switch_tab",lambda args,result:verify_browser_switch_tab_postcondition(browser,args,result))' in app_source
    assert 't.postconditions.register("browser_fill",lambda args,result:verify_browser_fill_postcondition(browser,args,result))' in app_source
    assert "self.learning.record_verified_runtime_outcome(payload)" in app_source
    assert "VerifiedGoalWorkflow(self.root_path,self.runtime,goals=self.goals,world=self.world)" in app_source


def test_verified_execution_promotes_capability_only_after_verifier_passes(tmp_path):
    manager = CapabilityManager(tmp_path)
    manager.register("desktop_click", "Click a desktop control", kind="runtime_tool")
    executor = VerifiedExecutor(
        ActionEngine(ActionStore(tmp_path / "actions")),
        capability_manager=manager,
    )

    result = executor.run(
        "click button",
        lambda: {"clicked": True},
        lambda value: Verification(True, {"observed": "button state changed"}, "state observed"),
        approval=True,
        capability="desktop_click",
    )

    assert result.status == "verified"
    assert manager.can_claim("desktop_click")
    assert manager.get("desktop_click")["success_count"] == 1


def test_unverified_execution_failure_updates_capability_without_success(tmp_path):
    manager = CapabilityManager(tmp_path)
    manager.register("send_message", "Send a message", kind="runtime_tool")
    executor = VerifiedExecutor(
        ActionEngine(ActionStore(tmp_path / "actions")),
        max_attempts=1,
        capability_manager=manager,
    )

    result = executor.run(
        "send message",
        lambda: {"sent": True},
        lambda _: Verification(False, None, "no outgoing message observed"),
        approval=True,
        capability="send_message",
    )

    capability = manager.get("send_message")
    assert result.status == "failed_verification"
    assert capability["success_count"] == 0
    assert capability["failure_count"] == 1
    assert capability["verified"] is False
    assert capability["status"] == "degraded"


def test_unapproved_action_does_not_change_capability_evidence(tmp_path):
    manager = CapabilityManager(tmp_path)
    manager.register("system_change", "Change a system setting", kind="runtime_tool")
    executor = VerifiedExecutor(
        ActionEngine(ActionStore(tmp_path / "actions")),
        capability_manager=manager,
    )

    result = executor.run(
        "change setting", lambda: None, lambda _: True,
        approval=False, capability="system_change",
    )

    assert result.status == "awaiting_approval"
    capability = manager.get("system_change")
    assert capability["success_count"] == capability["failure_count"] == 0
    assert capability["status"] == STATUS_UNVERIFIED


def test_agent_executor_keeps_unverified_side_effect_attempted(tmp_path):
    manager = CapabilityManager(tmp_path)
    tools = ToolRegistry(capability_manager=manager)
    tools.add("send_message", "Send a message", lambda: {"status": "sent"}, "external")
    executor = AgentExecutor(tools, capabilities=manager)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "send_message", "args": {}}]})[0]

    assert result["status"] == "attempted"
    assert result["verified"] is False
    assert manager.get("send_message")["verified"] is False


def test_agent_executor_does_not_trust_self_asserted_verifier_evidence(tmp_path):
    manager = CapabilityManager(tmp_path)
    tools = ToolRegistry(capability_manager=manager)
    tools.add(
        "observe_change", "Observe a state change",
        lambda: {"verified": True, "evidence": {"state_changed": True}}, "execute",
    )
    executor = AgentExecutor(tools, capabilities=manager)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "observe_change", "args": {}}]})[0]

    assert result["status"] == "attempted"
    assert result["verified"] is False
    assert result["result"]["tool_reported_verified"] is True
    assert result["result"]["verified"] is False
    assert manager.get("observe_change")["verified"] is False


def test_agent_executor_records_only_independent_postcondition_evidence(tmp_path):
    manager = CapabilityManager(tmp_path)
    tools = ToolRegistry(capability_manager=manager)
    tools.add(
        "observe_change", "Observe a state change",
        lambda: {"verified": True, "evidence": {"self_report": True}}, "execute",
    )
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register(
        "observe_change",
        lambda _args, _result: PostconditionResult(True, {"observed": True, "state_changed": True}, "state observed"),
    )
    executor = AgentExecutor(tools, capabilities=manager)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "observe_change", "args": {}}]})[0]

    assert result["status"] == "verified"
    assert result["verified"] is True
    assert result["result"]["evidence"] == {"observed": True, "state_changed": True}
    assert manager.can_claim("observe_change")


def test_devour_candidate_receipt_persists_without_claiming_runtime_availability(tmp_path):
    manager = CapabilityManager(tmp_path)
    receipt = manager.record_devour_candidate(
        "terminal_agent", candidate_version="ALICE v4.106.0",
        candidate_sha256="a" * 64, report_sha256="b" * 64, tree_sha256="c" * 64,
        capability_candidate_sha256="d" * 64,
        candidate_status="tested_candidate_isolated_pending_review",
        test_paths=["alice/tests/test_terminal_agent.py"], test_summary="1 passed",
        sandbox={"verified": True, "backend": "docker", "image_id": "sha256:" + "e" * 64,
                 "checks": {"network_disabled": True, "only_candidate_bind_mount": True}},
        approval_method="explicit_per_capability_ui_confirmation",
        entry_point="alice.adapters.terminal_agent:run_terminal_agent",
    )

    stored = manager.get("terminal_agent")
    assert receipt["recorded"] is True
    assert receipt["active"] is False and receipt["verified"] is False
    assert stored["kind"] == "acquired_candidate"
    assert stored["configured"] is False
    assert stored["verified"] is False and stored["status"] == STATUS_UNVERIFIED
    assert manager.has("terminal_agent") is False
    assert manager.can_claim("terminal_agent") is False
    assert stored["acquisition_evidence"][0]["sandbox"]["verified"] is True
    assert CapabilityManager(tmp_path).get("terminal_agent")["acquisition_evidence"] == stored["acquisition_evidence"]


def test_runtime_tool_registration_keeps_devour_receipt_but_does_not_verify_tool(tmp_path):
    manager = CapabilityManager(tmp_path)
    manager.record_devour_candidate(
        "terminal_agent", candidate_version="ALICE v4.106.0", candidate_sha256="a" * 64,
        report_sha256="b" * 64, tree_sha256="c" * 64, capability_candidate_sha256="d" * 64,
        candidate_status="tested_candidate_pending_isolation",
        test_paths=["alice/tests/test_terminal_agent.py"], test_summary="1 passed",
        sandbox={"verified": False}, approval_method="explicit_per_capability_ui_confirmation",
    )
    tools = ToolRegistry(capability_manager=manager)
    tools.add("terminal_agent", "Run a terminal task", lambda: {"ok": True}, "execute")

    stored = manager.get("terminal_agent")
    assert stored["kind"] == "runtime_tool"
    assert stored["configured"] is True
    assert stored["status"] == STATUS_UNVERIFIED and stored["verified"] is False
    assert manager.has("terminal_agent") is False
    assert len(stored["acquisition_evidence"]) == 1


def test_isolated_devour_receipt_requires_verified_sandbox_and_sha256(tmp_path):
    manager = CapabilityManager(tmp_path)
    with pytest.raises(ValueError, match="verified sandbox"):
        manager.record_devour_candidate(
            "terminal_agent", candidate_version="ALICE v4.106.0", candidate_sha256="a" * 64,
            report_sha256="b" * 64, tree_sha256="c" * 64, capability_candidate_sha256="d" * 64,
            candidate_status="tested_candidate_isolated_pending_review",
            test_paths=["alice/tests/test_terminal_agent.py"], test_summary="1 passed",
            sandbox={"verified": False}, approval_method="explicit_per_capability_ui_confirmation",
        )
    with pytest.raises(ValueError, match="candidate package SHA-256"):
        manager.record_devour_candidate(
            "terminal_agent", candidate_version="ALICE v4.106.0", candidate_sha256="invalid",
            report_sha256="b" * 64, tree_sha256="c" * 64, capability_candidate_sha256="d" * 64,
            candidate_status="tested_candidate_pending_isolation",
            test_paths=["alice/tests/test_terminal_agent.py"], test_summary="1 passed",
            sandbox={"verified": False}, approval_method="explicit_per_capability_ui_confirmation",
        )


def test_isolated_devour_receipt_requires_runtime_entry_point(tmp_path):
    manager = CapabilityManager(tmp_path)
    with pytest.raises(ValueError, match="declared runtime entry point"):
        manager.record_devour_candidate(
            "terminal_agent", candidate_version="ALICE v4.106.0", candidate_sha256="a" * 64,
            report_sha256="b" * 64, tree_sha256="c" * 64, capability_candidate_sha256="d" * 64,
            candidate_status="tested_candidate_isolated_pending_review",
            test_paths=["alice/tests/test_terminal_agent.py"], test_summary="1 passed",
            sandbox={"verified": True}, approval_method="explicit_per_capability_ui_confirmation",
        )
