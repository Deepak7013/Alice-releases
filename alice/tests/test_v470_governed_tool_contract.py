from alice.tools.governed_contract import ToolContract, ToolContractGate

def test_verified_read_tool_can_pass_contract():
    r=ToolContractGate().validate(ToolContract("read_screen",verified=True)); assert r["allowed"]

def test_write_tool_requires_permissions():
    r=ToolContractGate().validate(ToolContract("write_file",risk="write",verified=True)); assert not r["allowed"] and r["reason"]=="permissions_required"

def test_unverified_tool_cannot_pass():
    r=ToolContractGate().validate(ToolContract("shell",risk="execute",permissions=("workspace",),verified=False)); assert not r["allowed"] and r["reason"]=="tool_not_verified"

def test_invalid_risk_is_rejected():
    r=ToolContractGate().validate(ToolContract("x",risk="root",verified=True)); assert not r["allowed"] and r["reason"]=="invalid_risk"
