"""Discover installed Windows applications without hard-coding a small allowlist."""
from pathlib import Path
import csv
import os, subprocess, json

class AppDiscovery:
    @staticmethod
    def resolve_shortcut(shortcut_path):
        """Return an existing local EXE only for a simple argument-free .lnk target."""
        shortcut=Path(str(shortcut_path))
        if os.name!='nt' or shortcut.suffix.casefold()!='.lnk' or not shortcut.is_file():
            return None
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            try:
                shell=comtypes.client.CreateObject('WScript.Shell',dynamic=True)
                link=shell.CreateShortcut(str(shortcut))
                target_text=str(link.TargetPath or '').strip()
                arguments=str(link.Arguments or '').strip()
                del link, shell
            finally:
                comtypes.CoUninitialize()
            if not target_text or arguments or target_text.startswith('\\\\'):
                return None
            target=Path(target_text)
            if not target.is_absolute() or target.suffix.casefold()!='.exe':
                return None
            resolved=target.resolve(strict=True)
            return str(resolved) if resolved.is_file() else None
        except Exception:
            return None

    def _start_apps(self):
        roots = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        found=[]
        for root in roots:
            if not root.exists(): continue
            for p in root.rglob("*.lnk"):
                found.append({"name": p.stem, "path": str(p), "kind":"shortcut"})
            for p in root.rglob("*.exe"):
                found.append({"name": p.stem, "path": str(p), "kind":"exe"})
        return found

    def search(self, query="", limit=30):
        q=(query or "").lower().strip(); items=self._start_apps()
        if q: items=[x for x in items if q in x["name"].lower()]
        seen=set(); out=[]
        for x in sorted(items,key=lambda z:z["name"].lower()):
            k=(x["name"].lower(),x["path"].lower())
            if k not in seen:
                seen.add(k)
                row=dict(x)
                if row.get("kind")=="shortcut" and q:
                    target=self.resolve_shortcut(row["path"])
                    if target:
                        row["launch_path"]=target
                out.append(row)
            if len(out)>=int(limit): break
        return {"ok":True,"apps":out}

    def running(self, query=""):
        try:
            raw=subprocess.check_output(["tasklist","/FO","CSV","/NH"],text=True,errors="replace")
        except Exception as e: return {"ok":False,"error":str(e)}
        rows=[]; q=(query or "").lower()
        for line in raw.splitlines():
            if q and q not in line.lower(): continue
            rows.append(line)
        return {"ok":True,"processes":rows[:100]}

    def process_by_pid(self, pid):
        """Read one process row by exact PID using tasklist's native filter."""
        try:
            value=int(pid)
            if value<=0:
                return {"ok":False,"error":"invalid_pid"}
            raw=subprocess.check_output(
                ["tasklist","/FO","CSV","/NH","/FI",f"PID eq {value}"],
                text=True,errors="replace")
        except Exception as e:
            return {"ok":False,"error":type(e).__name__}
        rows=[]
        for line in raw.splitlines():
            row=next(csv.reader([line]),[])
            if len(row)>=2 and row[1].strip().isdigit() and int(row[1])==value:
                rows.append({"image":row[0].strip(),"pid":value})
        return {"ok":True,"processes":rows}
