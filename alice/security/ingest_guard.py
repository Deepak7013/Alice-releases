"""Static ingestion guard for external repositories. Never executes imported code."""
from __future__ import annotations
import hashlib,re
from pathlib import Path

class IngestGuard:
    PATTERNS=[
        ("credential_access",re.compile(r"(?i)\b(password|api[_-]?key|secret|token|cookie|credential)\b")),
        ("destructive_command",re.compile(r"(?i)\b(?:rm\s+-rf|format\s+[a-z]:|del\s+/[sq]|shutdown|diskpart|reg\s+delete)\b")),
        ("persistence",re.compile(r"(?i)\b(?:schtasks|scheduled\s+task|startup|run\s*key|service\s+create)\b")),
        ("obfuscation",re.compile(r"(?i)\b(?:base64|powershell\s+-enc|invoke-expression|eval\s*\(|exec\s*\()\b")),
        ("network_download",re.compile(r"(?i)\b(?:curl|wget|invoke-webrequest|requests\.get|urllib\.request)\b")),
    ]
    def digest_tree(self,path):
        p=Path(path); h=hashlib.sha256()
        for f in sorted(x for x in p.rglob("*") if not x.is_symlink() and x.is_file() and ".git" not in x.parts):
            h.update(f.relative_to(p).as_posix().encode()); h.update(f.read_bytes())
        return h.hexdigest()
    def scan_tree(self,path):
        p=Path(path); findings=[]; files_scanned=0; symlinks_skipped=0
        for f in p.rglob("*"):
            if f.is_symlink():
                symlinks_skipped+=1
                continue
            if not f.is_file() or ".git" in f.parts: continue
            try:
                if f.stat().st_size>2_000_000: continue
                text=f.read_text(errors="replace")
            except Exception: continue
            files_scanned+=1
            for kind,rx in self.PATTERNS:
                m=rx.search(text)
                if m:
                    findings.append({"type":kind,"path":f.relative_to(p).as_posix(),"sample":m.group(0)[:80]})
        return {"files_scanned":files_scanned,"symlinks_skipped":symlinks_skipped,
                "threat_count":len(findings),"findings":findings[:500],
                "policy":"static findings are not proof of malware; suspicious content remains quarantined and unexecuted"}
