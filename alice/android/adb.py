from __future__ import annotations
import subprocess,shlex
class ADBError(RuntimeError): pass
class ADBAdapter:
    def __init__(self,adb='adb'): self.adb=adb
    def _run(self,*args,timeout=15):
        try:r=subprocess.run([self.adb,*args],capture_output=True,text=True,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired) as e: raise ADBError(str(e))
        if r.returncode: raise ADBError(r.stderr.strip() or 'adb command failed')
        return r.stdout.strip()
    def devices(self):
        out=self._run('devices'); return [line.split('	')[0] for line in out.splitlines()[1:] if '	device' in line]
    def shell(self,device,command): return self._run('-s',device,'shell',command)
    def launch(self,device,package): return self.shell(device,f'monkey -p {shlex.quote(package)} 1')

    def push(self,device,local,remote):
        return self._run("-s",device,"push",str(local),remote,timeout=60)
    def pull(self,device,remote,local):
        return self._run("-s",device,"pull",remote,str(local),timeout=60)
