"""Controlled Android device support through the user's locally connected ADB device."""
import subprocess, tempfile
from pathlib import Path

class AndroidController:
    def __init__(self, adb="adb"):
        self.adb = adb

    def _run(self, *args, timeout=30, check=True):
        p = subprocess.run([self.adb, *map(str,args)], capture_output=True, text=True, timeout=timeout)
        if check and p.returncode:
            raise RuntimeError((p.stderr or p.stdout or "adb command failed").strip())
        return p

    def devices(self):
        p=self._run("devices", check=False)
        rows=[]
        for line in p.stdout.splitlines()[1:]:
            parts=line.split()
            if len(parts)>=2: rows.append({"serial":parts[0],"state":parts[1]})
        return {"ok":p.returncode==0,"devices":rows,"error":p.stderr.strip()}

    def _serial_args(self, serial=None): return (["-s",serial] if serial else [])

    def shell(self, command, serial=None):
        if isinstance(command,(list,tuple)): args=list(command)
        else: args=["sh","-lc",str(command)]
        p=self._run(*self._serial_args(serial),"shell",*args,timeout=60,check=False)
        return {"ok":p.returncode==0,"stdout":p.stdout,"stderr":p.stderr,"returncode":p.returncode}

    def screenshot(self, path=None, serial=None):
        if path is None: path=str(Path(tempfile.gettempdir())/"alice_android_screen.png")
        remote="/sdcard/__alice_screen.png"
        p=subprocess.run([self.adb,*self._serial_args(serial),"exec-out","screencap","-p"],capture_output=True,timeout=30)
        if p.returncode: raise RuntimeError((p.stderr or b"screencap failed").decode(errors="replace"))
        Path(path).write_bytes(p.stdout)
        return {"ok":True,"path":path}

    def tap(self,x,y,serial=None):
        return self.shell(["input","tap",int(x),int(y)],serial)

    def swipe(self,x1,y1,x2,y2,duration_ms=400,serial=None):
        return self.shell(["input","swipe",int(x1),int(y1),int(x2),int(y2),int(duration_ms)],serial)

    def keyevent(self,key,serial=None): return self.shell(["input","keyevent",str(key)],serial)

    def text(self,text,serial=None):
        safe=str(text).replace(" ","%s").replace("&","%26").replace(";","%3B")
        return self.shell(["input","text",safe],serial)

    def launch_package(self,package,serial=None):
        if not package or any(c in str(package) for c in " ;|&\n\r"): raise ValueError("Invalid Android package")
        return self.shell(["monkey","-p",str(package),"1"],serial)

    def current_activity(self,serial=None):
        return self.shell(["dumpsys","activity","activities"],serial)
