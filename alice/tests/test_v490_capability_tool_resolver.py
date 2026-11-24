from alice.execution.capability_tool_resolver import CapabilityToolResolver


def cap(**kw):
    base = {"name":"computer_control","enabled":True,"configured":True,
            "status":"available","verified":True}
    base.update(kw); return base


def tool(**kw):
    base = {"name":"desktop_tool","capabilities":["computer_control"],
            "risk":"read","verified":True,"permissions":[]}
    base.update(kw); return base


def test_selects_verified_governed_tool():
    r=CapabilityToolResolver().resolve(cap(), [tool()])
    assert r.allowed and r.selected=="desktop_tool"


def test_unverified_capability_is_blocked():
    r=CapabilityToolResolver().resolve(cap(verified=False), [tool()])
    assert not r.allowed and r.reason=="capability_not_verified"


def test_unverified_tool_is_not_selected():
    r=CapabilityToolResolver().resolve(cap(), [tool(verified=False)])
    assert not r.allowed and r.reason=="no_governed_tool"


def test_write_tool_requires_permission_metadata():
    r=CapabilityToolResolver().resolve(cap(), [tool(risk="write", permissions=[])])
    assert not r.allowed and r.reason=="no_governed_tool"


def test_invalid_tool_risk_is_ignored():
    r=CapabilityToolResolver().resolve(cap(), [tool(risk="root")])
    assert not r.allowed and r.reason=="no_governed_tool"


def test_multiple_candidates_are_deterministically_ranked():
    r=CapabilityToolResolver().resolve(cap(), [tool(name="z_tool"), tool(name="a_tool")])
    assert r.allowed and r.selected=="a_tool" and r.candidates==("a_tool","z_tool")
