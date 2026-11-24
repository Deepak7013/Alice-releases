
"""Artifact quality checks for native Alice outputs."""
from pathlib import Path
import zipfile, re

class ArtifactQA:
    REQUIRED={"word":".docx","excel":".xlsx","powerpoint":".pptx","pdf":".pdf","markdown":".md","text":".txt"}
    def inspect(self,path,kind=None):
        p=Path(path)
        if not p.exists() or p.stat().st_size==0: return {"ok":False,"reason":"missing_or_empty"}
        kind=(kind or self._kind(p)).lower()
        if kind in {"word","excel","powerpoint"}:
            if not zipfile.is_zipfile(p): return {"ok":False,"reason":"invalid_office_package"}
            names=set(zipfile.ZipFile(p).namelist())
            required={"word/document.xml"} if kind=="word" else {"xl/workbook.xml"} if kind=="excel" else {"ppt/presentation.xml"}
            if not required.issubset(names): return {"ok":False,"reason":"missing_core_part"}
        elif kind=="pdf":
            if p.read_bytes()[:5]!=b"%PDF-": return {"ok":False,"reason":"invalid_pdf_header"}
        elif kind in {"markdown","text"}:
            p.read_text(encoding="utf-8")
        return {"ok":True,"kind":kind,"bytes":p.stat().st_size}
    def _kind(self,p):
        return {".docx":"word",".xlsx":"excel",".pptx":"powerpoint",".pdf":"pdf",".md":"markdown",".txt":"text"}.get(p.suffix.lower(),"unknown")
    def inspect_many(self,items):
        results=[self.inspect(*item) if isinstance(item,tuple) else self.inspect(item) for item in items]
        return {"ok":all(x["ok"] for x in results),"results":results}
