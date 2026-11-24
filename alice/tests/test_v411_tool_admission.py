from alice.execution.tool_admission import ToolAdmissionGate
from alice.tools.governed_contract import ToolContract


def cap(**kw):
    base = {"name": "computer_control", "verified": True}
    base.update(kw)
    return base


def tool(**kw):
    base = {"name": "desktop_tool", "capabilities": ["computer_control"], "verified": True}
    base.update(kw)
    return base


def contract(**kw):
    base = {"name": "desktop_tool", "risk": "read", "verified": True}
    base.update(kw)
    return ToolContract(**base)


def test_admits_verified_matching_tool():
    r = ToolAdmissionGate().admit(capability=cap(), tool=tool(), contract=contract())
    assert r.admitted and r.tool == "desktop_tool"


def test_rejects_missing_capability():
    r = ToolAdmissionGate().admit(capability={}, tool=tool(), contract=contract())
    assert not r.admitted and r.reason == "missing_capability"


def test_rejects_contract_name_mismatch():
    r = ToolAdmissionGate().admit(capability=cap(), tool=tool(), contract=contract(name="other"))
    assert not r.admitted and r.reason == "tool_contract_name_mismatch"


def test_rejects_capability_tool_mismatch():
    r = ToolAdmissionGate().admit(capability=cap(), tool=tool(capabilities=["browser"]), contract=contract())
    assert not r.admitted and r.reason == "capability_tool_mismatch"


def test_rejects_unverified_tool():
    r = ToolAdmissionGate().admit(capability=cap(), tool=tool(verified=False), contract=contract())
    assert not r.admitted and r.reason == "tool_not_verified"


def test_rejects_unverified_capability():
    r = ToolAdmissionGate().admit(capability=cap(verified=False), tool=tool(), contract=contract())
    assert not r.admitted and r.reason == "capability_not_verified"


def test_rejects_invalid_contract():
    r = ToolAdmissionGate().admit(
        capability=cap(), tool=tool(), contract=contract(risk="execute", permissions=())
    )
    assert not r.admitted and r.reason == "permissions_required"
