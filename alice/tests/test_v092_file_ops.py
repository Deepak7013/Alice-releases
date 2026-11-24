from alice.devices.file_ops import CrossDeviceFiles
class C:
    connected=True; endpoint="abc"
class M:
    def get(self,d): return C()
class A:
    def shell(self,d,c): return c
    def push(self,d,l,r): return "pushed"
    def pull(self,d,r,l): return "pulled"
def test_list(tmp_path): assert CrossDeviceFiles(A(),M()).list("x","/sdcard").startswith("ls -la")
def test_push(tmp_path): assert CrossDeviceFiles(A(),M()).push("x","a","/sdcard/a")=="pushed"
def test_traversal_rejected(tmp_path):
    try: CrossDeviceFiles(A(),M()).read("x","/sdcard/../secret")
    except ValueError:pass
    else:assert False
def test_relative_rejected(tmp_path):
    try: CrossDeviceFiles(A(),M()).list("x","sdcard")
    except ValueError:pass
    else:assert False
