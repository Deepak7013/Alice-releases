
import subprocess
from pathlib import Path
from ..security.permissions import PermissionManager

class WindowsTerminal:
    def __init__(self):
        self.permissions=PermissionManager()

    def run(self, command, timeout=120, cwd=None):
        # Alice can generate arbitrary commands, but the permission manager
        # decides whether execution needs explicit approval.
        if not self.permissions.is_safe_command(command):
            if not self.permissions.request_command(command):
                return {"status":"denied","command":command}

        workdir=str(Path(cwd).resolve()) if cwd else None
        p=subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=int(timeout)
        )
        return {
            "status":"ok" if p.returncode==0 else "failed",
            "returncode":p.returncode,
            "stdout":p.stdout[-20000:],
            "stderr":p.stderr[-20000:],
            "command":command
        }
