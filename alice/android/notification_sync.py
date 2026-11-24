from __future__ import annotations
import json, subprocess
class AndroidNotificationSync:
    def __init__(self, adb, mirror): self.adb,self.mirror=adb,mirror
    def sync(self, device_id, package_filter=None):
        # Uses Android's authorized notification listener output when available.
        raw=self.adb.shell(device_id, "cmd notification list --noredact")
        count=0
        for line in str(raw).splitlines():
            if package_filter and package_filter not in line: continue
            if "|" not in line: continue
            parts=[x.strip() for x in line.split("|",2)]
            if len(parts)==3:
                self.mirror.ingest(parts[0],parts[1],parts[2]); count+=1
        return {"synced":count}
