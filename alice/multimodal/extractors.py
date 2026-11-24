from __future__ import annotations
import hashlib, mimetypes, re
from pathlib import Path

IMAGE_EXTS={".png",".jpg",".jpeg",".webp",".bmp",".gif"}
DOC_EXTS={".txt",".md",".rst",".py",".json",".csv",".xml",".html",".htm",".docx"}


def classify(path: str):
    p=Path(path); ext=p.suffix.lower(); mime=mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if ext in IMAGE_EXTS: return "image", mime
    if ext==".pdf": return "pdf", mime
    if ext==".svg": return "svg", "image/svg+xml"
    if ext in DOC_EXTS: return "document", mime
    return "unknown", mime


def digest(path: str) -> str:
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def text_from_file(path: str, max_chars: int=50000):
    p=Path(path); kind,_=classify(path)
    if kind=="pdf":
        from pypdf import PdfReader
        reader=PdfReader(str(p)); pages=len(reader.pages); parts=[]
        for page in reader.pages:
            try: parts.append(page.extract_text() or "")
            except Exception: parts.append("")
            if sum(map(len,parts))>=max_chars: break
        return "\n\n".join(parts)[:max_chars], pages
    if p.suffix.lower()==".docx":
        from docx import Document
        doc=Document(str(p)); text="\n".join(x.text for x in doc.paragraphs)
        return text[:max_chars], None
    return p.read_text(encoding="utf-8",errors="replace")[:max_chars], None


def screen_capture(path: str):
    from alice.vision.screen import screenshot
    return screenshot(path)
