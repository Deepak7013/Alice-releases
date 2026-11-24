import pytest
from alice.engineering.gate import SelfEngineeringGate
from alice.maintenance.self_manager import SelfManager


def test_gate_reports_low_risk_small_patch(tmp_path):
    root=tmp_path
    (root/'alice').mkdir()
    (root/'alice'/'x.py').write_text('VALUE=1\n')
    g=SelfEngineeringGate()
    impact=g.preflight(root,[{'path':'alice/x.py','content':'VALUE=2\n'}])
    assert impact['risk']=='low'
    assert impact['changed_lines']==2


def test_gate_blocks_invalid_python(tmp_path):
    root=tmp_path
    (root/'alice').mkdir()
    g=SelfEngineeringGate()
    with pytest.raises(ValueError,match='blocked'):
        g.preflight(root,[{'path':'alice/x.py','content':'def broken(:\n'}])


def test_self_manager_returns_impact_on_candidate_failure(tmp_path):
    root=tmp_path
    (root/'alice').mkdir()
    (root/'alice'/'feature.py').write_text('VALUE=1\n')
    lab=SelfManager(root)
    lab.run_tests=lambda cwd=None:type('R',(),{'returncode':1,'stdout':'','stderr':'failed'})()
    result=lab.apply_patch([{'path':'alice/feature.py','content':'VALUE=2\n'}])
    assert result['ok'] is False
    assert result['impact']['risk']=='low'
