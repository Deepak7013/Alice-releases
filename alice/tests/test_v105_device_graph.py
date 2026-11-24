import json

import pytest

from alice.agent.executor import Executor as AgentExecutor
from alice.devices.graph import DeviceGraph, DeviceGraphError
from alice.devices.registry import DeviceRegistry
from alice.execution.postconditions import PostconditionRegistry
from alice.tools.registry import ToolRegistry


def _graph(tmp_path):
    registry = DeviceRegistry(tmp_path)
    registry.register("Windows laptop", "computer", ["desktop"], device_id="pc-1")
    registry.register("Android phone", "android", ["messaging"], device_id="phone-1")
    return registry, DeviceGraph(tmp_path, registry)


def test_snapshot_projects_registered_devices_without_granting_authority(tmp_path):
    _registry, graph = _graph(tmp_path)

    result = graph.snapshot()

    assert [row["id"] for row in result["nodes"]] == ["pc-1", "phone-1"]
    assert result["edges"] == []
    assert result["authority_granted"] is False
    assert result["requires_device_consent"] is True


def test_user_declared_links_persist_and_advisory_routes_are_not_executable(tmp_path):
    registry, graph = _graph(tmp_path)

    first = graph.link("pc-1", "phone-1", "connected_via")
    second = graph.link("pc-1", "phone-1", "connected_via")
    route = DeviceGraph(tmp_path, registry).route("pc-1", "phone-1")

    assert first["edge_id"] == second["edge_id"]
    assert len(graph.snapshot()["edges"]) == 1
    assert route["path"] == ["pc-1", "phone-1"]
    assert route["executable"] is False
    assert route["requires_device_consent"] is True
    assert registry.get("pc-1")["paired"] is False
    assert registry.get("phone-1")["paired"] is False


def test_relationships_cannot_authorize_or_impersonate_device_control(tmp_path):
    _registry, graph = _graph(tmp_path)

    with pytest.raises(DeviceGraphError, match="Unsupported advisory"):
        graph.link("pc-1", "phone-1", "controls")
    with pytest.raises(DeviceGraphError, match="Both graph endpoints"):
        graph.link("pc-1", "unknown", "connected_via")
    with pytest.raises(DeviceGraphError, match="cannot be linked to itself"):
        graph.link("pc-1", "pc-1", "associated_with")


def test_only_connected_via_relationships_participate_in_advisory_route(tmp_path):
    _registry, graph = _graph(tmp_path)
    graph.link("pc-1", "phone-1", "mirrors")

    route = graph.route("pc-1", "phone-1")

    assert route["found"] is False
    assert route["executable"] is False
    assert route["requires_device_consent"] is True


def test_link_postcondition_reads_persisted_non_authorizing_edge(tmp_path):
    _registry, graph = _graph(tmp_path)
    args = {"source_id": "pc-1", "target_id": "phone-1", "relation": "connected_via"}
    result = graph.link(**args)

    verified = graph.verify_link_postcondition(args, result)

    assert verified.ok is True
    assert verified.evidence["observed"] is True
    assert verified.evidence["authority_granted"] is False

    stored = json.loads(graph.path.read_text(encoding="utf-8"))
    stored["edges"][0]["grants_authority"] = True
    graph.path.write_text(json.dumps(stored), encoding="utf-8")
    rejected = graph.verify_link_postcondition(args, result)
    assert rejected.ok is False
    assert rejected.evidence["edge_present"] is False


def test_active_tool_verifies_graph_write_after_disk_readback(tmp_path):
    _registry, graph = _graph(tmp_path)
    tools = ToolRegistry()
    tools.add("device_graph_link", "Record advisory link", graph.link, "write")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register("device_graph_link", graph.verify_link_postcondition)
    executor = AgentExecutor(tools)
    executor.permissions.needs_confirmation = lambda _name, _args: False

    result = executor.run({"steps": [{"tool": "device_graph_link", "args": {
        "source_id": "pc-1", "target_id": "phone-1", "relation": "connected_via",
    }}]})[0]

    assert result["status"] == "verified"
    assert result["postcondition"]["evidence"]["edge_present"] is True
    assert result["postcondition"]["evidence"]["authority_granted"] is False
