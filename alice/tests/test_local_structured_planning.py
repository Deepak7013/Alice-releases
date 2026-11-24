import json
from types import SimpleNamespace

import pytest

from alice.agent.planner import Planner
from alice.providers.router import ProviderError, Router
from alice.tools.registry import ToolRegistry


def router_with_reply(content, finish_reason="stop"):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason=finish_reason, message=SimpleNamespace(content=content))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    router = Router.__new__(Router)
    router.local_base = "http://localhost:11434/v1"
    router.local_model = "llama3.2:latest"
    router._order = lambda: ["local"]
    router._openai_client = lambda *args: client
    router._safe_max_tokens = lambda prompt, maximum: maximum
    router._record_success = lambda *args: None
    router._record_failure = lambda *args: None
    return router, calls


def registry():
    tools = ToolRegistry()
    tools.add("multiply_numbers", "Args: a and b, integers", lambda a, b: a * b, "read")
    return tools


def test_router_requests_local_schema_constrained_output():
    payload = {"goal": "calculate", "done": False, "steps": [
        {"tool": "multiply_numbers", "args": {"a": 17, "b": 19}}]}
    router, calls = router_with_reply(json.dumps(payload))
    plan = Planner(router, registry()).plan("multiply 17 by 19")
    assert plan["steps"][0]["args"] == {"a": 17, "b": 19}
    request = calls[0]
    assert request["model"] == "llama3.2:latest"
    assert request["temperature"] == 0
    schema = request["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["steps"]["items"]["properties"]["tool"]["enum"] == ["multiply_numbers"]


@pytest.mark.parametrize("content,reason", [("not JSON", "stop"), ("{} {}", "stop"), ("[]", "stop"), ("{}", "length")])
def test_malformed_or_truncated_output_fails_without_unstructured_retry(content, reason):
    router, calls = router_with_reply(content, reason)
    with pytest.raises(ProviderError, match="structured planning failed"):
        Planner(router, registry()).plan("calculate")
    assert len(calls) == 1


@pytest.mark.parametrize("endpoint,model", [
    ("https://example.com/v1", "llama3.2:latest"),
    ("http://localhost:11434/v1", "model:cloud"),
    ("http://user:password@localhost:11434/v1", "llama3.2:latest"),
])
def test_hosted_or_credential_bearing_endpoints_are_not_contacted(endpoint, model):
    router, calls = router_with_reply("{}")
    router.local_base, router.local_model = endpoint, model
    with pytest.raises(ProviderError, match="on-PC local model"):
        router.ask_json("calculate", {})
    assert calls == []


def test_proposed_steps_cannot_be_marked_complete_before_execution():
    router, _ = router_with_reply(json.dumps({"goal": "multiply", "done": True,
        "steps": [{"tool": "multiply_numbers", "args": {"a": 17, "b": 19}}]}))
    assert Planner(router, registry()).plan("calculate")["done"] is False


@pytest.mark.parametrize("steps", [
    [{"tool": "unknown", "args": {}}],
    [{"tool": "multiply_numbers", "args": [17, 19]}],
    [{"tool": "multiply_numbers", "args": {}}] * 9,
])
def test_application_validation_rejects_invalid_tool_plans(steps):
    router, _ = router_with_reply(json.dumps({"goal": "calculate", "done": False, "steps": steps}))
    with pytest.raises(ValueError):
        Planner(router, registry()).plan("calculate")
