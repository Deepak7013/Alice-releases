from __future__ import annotations
from pathlib import Path
from .adb import ADBAdapter, ADBError
class ADBControlAdapter(ADBAdapter):
    def screenshot(self, device, output_path=None):
        if output_path is None: raise ValueError("output_path required")
        p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True)
        # adb exec-out is intentionally used only for an explicitly requested local file.
        import subprocess
        try:
            r=subprocess.run([self.adb,"-s",device,"exec-out","screencap","-p"],capture_output=True,timeout=20)
        except (OSError,subprocess.TimeoutExpired) as e: raise ADBError(str(e))
        if r.returncode: raise ADBError(r.stderr.decode(errors="replace").strip() or "screenshot failed")
        p.write_bytes(r.stdout); return str(p)
