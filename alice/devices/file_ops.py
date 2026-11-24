from __future__ import annotations
import posixpath
class CrossDeviceFiles:
    def __init__(self, adb, connections): self.adb,self.connections=adb,connections
    def _target(self, device_id):
        c=self.connections.get(device_id)
        if not c or not c.connected: raise ConnectionError("device not connected")
        return c.endpoint
    @staticmethod
    def _safe(path):
        raw=str(path)
        if not raw.startswith("/") or any(part==".." for part in raw.split("/")):
            raise ValueError("unsafe device path")
        p=posixpath.normpath(raw)
        if not p.startswith("/") or p=="..": raise ValueError("unsafe device path")
        return p
    def list(self, device_id, path="/sdcard"):
        return self.adb.shell(self._target(device_id),f"ls -la {self._safe(path)}")
    def read(self, device_id, path):
        return self.adb.shell(self._target(device_id),f"cat {self._safe(path)}")
    def push(self, device_id, local, remote):
        return self.adb.push(self._target(device_id),local,self._safe(remote))
    def pull(self, device_id, remote, local):
        return self.adb.pull(self._target(device_id),self._safe(remote),local)
