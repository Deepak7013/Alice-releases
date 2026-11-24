"""Phase 11 safe capability acquisition: inspect and reimplement, never execute archive code."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import hashlib, zipfile

@dataclass
class DevourReport:
    source: str
    sha256: str
    files: int
    source_lines: int = 0
    capabilities: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    executed: bool = False

class SafeDevour:
    VERSION="v3.43.0"
    def inspect_zip(self, path: str | Path) -> DevourReport:
        p=Path(path); data=p.read_bytes()
        caps=[]; rejected=[]; lines=0
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if n.startswith("/") or ".." in Path(n).parts:
                    rejected.append(n); continue
                low=n.lower()
                if low.endswith(('.py','.rs','.js','.ts','.go','.java')):
                    try: lines += len(z.read(n).decode('utf-8','ignore').splitlines())
                    except Exception: pass
                for key,cap in [('browser','browser automation'),('mcp','MCP integration'),('session','session persistence'),('permission','permission controls'),('agent','agent orchestration')]:
                    if key in low and cap not in caps: caps.append(cap)
        return DevourReport(str(p),hashlib.sha256(data).hexdigest(),len(z.namelist()),lines,caps,rejected,False)
