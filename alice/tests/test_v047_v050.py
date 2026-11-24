import tempfile
from pathlib import Path
from alice.security.audit_chain import AuditChain
from alice.resources import ResourceManager,ResourceBudget
from alice.deployment import DeploymentManager,DeploymentProfile
from alice.integration import AliceIntegration

def test_audit_chain():
    with tempfile.TemporaryDirectory() as d:
        a=AuditChain(Path(d)/'a.jsonl'); a.append('decision',allowed=True); a.append('action',name='x'); assert a.verify()

def test_audit_tamper_detected():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'a.jsonl'; a=AuditChain(p); a.append('x',v=1); p.write_text(p.read_text().replace('"v": 1','"v": 2')); assert not a.verify()

def test_resource_budget():
    r=ResourceManager(ResourceBudget(max_parallel=1)); assert r.acquire('a','cpu'); assert r.acquire('b','cpu') is None; assert r.release('a','cpu')

def test_resource_reuse():
    r=ResourceManager(); x=r.acquire('a','browser'); y=r.acquire('a','browser'); assert x is y

def test_deployment_preflight():
    d=DeploymentManager(DeploymentProfile('Windows','3.12.0','production',True)); assert d.preflight()['ok'] and d.safe_for_autostart()

def test_integration_ready():
    with tempfile.TemporaryDirectory() as d:
        a=AuditChain(Path(d)/'audit.jsonl'); a.append('boot'); s=AliceIntegration(audit_chain=a).status(); assert s.ready and s.audit_ok
