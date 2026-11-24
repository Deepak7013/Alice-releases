from __future__ import annotations
from pathlib import Path
import importlib, tempfile
from .models import ComponentCheck, HealthReport

class HealthDiagnostics:
    """Non-invasive self-test runner. It never grants permissions or mutates protected source."""
    CORE=['alice.memory_context','alice.creation','alice.engineering','alice.orchestration','alice.security','alice.voice','alice.android_intelligence','alice.proactive','alice.resources','alice.deployment','alice.integration']
    def __init__(self, root=None): self.root=Path(root or Path.cwd())
    def check_imports(self):
        out=[]
        for name in self.CORE:
            try: importlib.import_module(name); out.append(ComponentCheck(name,True,'import ok',critical=True))
            except Exception as e: out.append(ComponentCheck(name,False,str(e),critical=True))
        return out
    def check_workspace(self):
        try:
            with tempfile.TemporaryDirectory(dir=self.root if self.root.exists() else None) as d:
                p=Path(d)/'health.txt'; p.write_text('ok',encoding='utf-8'); assert p.read_text(encoding='utf-8')=='ok'
            return ComponentCheck('workspace',True,'read/write ok',critical=True)
        except Exception as e: return ComponentCheck('workspace',False,str(e),critical=True)
    def run(self): return HealthReport(self.check_imports()+[self.check_workspace()])
