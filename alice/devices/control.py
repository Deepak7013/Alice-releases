from __future__ import annotations
class AndroidControl:
    def __init__(self, adb, connection_manager):
        self.adb, self.connections=adb, connection_manager
    def _target(self, device_id):
        c=self.connections.get(device_id)
        if not c or not c.connected: raise ConnectionError("device not connected")
        return c.endpoint
    def screenshot(self, device_id, output_path=None):
        target=self._target(device_id)
        return self.adb.screenshot(target, output_path)
    def tap(self, device_id, x, y):
        return self.adb.shell(self._target(device_id), f"input tap {int(x)} {int(y)}")
    def swipe(self, device_id, x1,y1,x2,y2,duration_ms=300):
        return self.adb.shell(self._target(device_id), f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration_ms)}")
    def text(self, device_id, value):
        safe=str(value).replace(" ","%s").replace("'","\\'")
        return self.adb.shell(self._target(device_id), f"input text {safe}")
    def back(self, device_id): return self.adb.shell(self._target(device_id),"input keyevent 4")
    def home(self, device_id): return self.adb.shell(self._target(device_id),"input keyevent 3")
