"""Automated rendered-artifact QA.

Uses LibreOffice for faithful Office rendering when available.  When LibreOffice
is unavailable, Alice uses a deterministic Python preview renderer for DOCX/XLSX/PPTX
and a direct-copy path for PDF.  The fallback is intentionally labeled as a
structural preview, not as a substitute for Office's exact layout engine.
"""
from pathlib import Path
import os, shutil, subprocess, tempfile, zipfile

class VisualArtifactQA:
    def __init__(self, timeout=60):
        self.timeout=timeout
        self.office=self._find_office()

    @staticmethod
    def _find_office():
        candidates = [shutil.which("libreoffice"), shutil.which("soffice")]
        if os.name == "nt":
            candidates += [
                os.path.join(os.environ.get("PROGRAMFILES", r"C:\\Program Files"), "LibreOffice", "program", "soffice.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\\Program Files (x86)"), "LibreOffice", "program", "soffice.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "LibreOffice", "program", "soffice.exe"),
            ]
        return next((p for p in candidates if p and Path(p).exists()), None)

    def _python_preview(self, path, out_dir):
        """Create a deterministic PDF preview without external Office software."""
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
        from reportlab.lib.utils import simpleSplit

        p=Path(path); out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
        pdf=out/(p.stem+".pdf")
        c=canvas.Canvas(str(pdf), pagesize=letter)
        width,height=letter
        margin=.6*inch
        y=height-margin
        c.setTitle(f"Alice preview: {p.name}")
        c.setFont("Helvetica-Bold",16)
        c.drawString(margin,y,f"Alice preview — {p.name}")
        y-=.35*inch
        c.setFont("Helvetica",9)
        c.drawString(margin,y,"Deterministic Python preview (LibreOffice not available).")
        y-=.3*inch

        def line(text, bold=False, size=10):
            nonlocal y
            c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            for part in simpleSplit(str(text), "Helvetica-Bold" if bold else "Helvetica", size, width-2*margin):
                if y < margin:
                    c.showPage(); y=height-margin; c.setFont("Helvetica",size)
                c.drawString(margin,y,part); y-=size+5

        kind = {".docx":"word", ".xlsx":"excel", ".pptx":"powerpoint"}.get(p.suffix.lower())
        if kind == "word":
            from docx import Document
            doc=Document(str(p))
            for para in doc.paragraphs:
                text=para.text.strip()
                if text: line(text, bold=para.style.name.lower().startswith("heading"))
            for table in doc.tables:
                line(" | ".join(cell.text.strip() for cell in table.rows[0].cells), bold=True)
                for row in table.rows[1:]: line(" | ".join(cell.text.strip() for cell in row.cells))
        elif kind == "excel":
            from openpyxl import load_workbook
            wb=load_workbook(str(p), data_only=False, read_only=True)
            for ws in wb.worksheets:
                line(f"Sheet: {ws.title}", bold=True)
                for row in ws.iter_rows(values_only=True):
                    vals=["" if v is None else str(v) for v in row]
                    if any(vals): line(" | ".join(vals))
        elif kind == "powerpoint":
            from pptx import Presentation
            prs=Presentation(str(p))
            for idx,slide in enumerate(prs.slides,1):
                if idx>1: c.showPage(); y=height-margin
                line(f"Slide {idx}", bold=True, size=13)
                for shape in slide.shapes:
                    if hasattr(shape,"text") and shape.text.strip(): line(shape.text.strip())
        else:
            c.save()
            return {"ok":False,"reason":"unsupported_fallback","rendered":[]}
        c.save()
        if not pdf.exists() or pdf.stat().st_size==0:
            return {"ok":False,"reason":"empty_fallback_render","rendered":[]}
        return {"ok":True,"reason":"python_preview","rendered":[str(pdf)],"bytes":pdf.stat().st_size,"renderer":"python_preview"}

    def render(self, path, out_dir):
        p=Path(path); out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
        # PDF is already a renderable inspection target; do not require Office.
        if p.suffix.lower()==".pdf":
            pdf=out/p.name
            shutil.copy2(p,pdf)
            return {"ok":True,"rendered":[str(pdf)],"bytes":pdf.stat().st_size,"renderer":"direct_pdf"}
        if not self.office:
            return self._python_preview(p,out)
        try:
            subprocess.run([self.office,"--headless","--convert-to","pdf","--outdir",str(out),str(p)],
                           check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           timeout=self.timeout)
        except Exception as e:
            # If Office exists but cannot render this file, use the deterministic
            # fallback before reporting failure.
            fallback=self._python_preview(p,out)
            if fallback.get("ok"):
                fallback["office_error"]=str(e)
                return fallback
            return {"ok":False,"reason":"render_failed","error":str(e),"rendered":[]}
        pdf=out/(p.stem+".pdf")
        if not pdf.exists() or pdf.stat().st_size==0:
            fallback=self._python_preview(p,out)
            if fallback.get("ok"): return fallback
            return {"ok":False,"reason":"empty_render","rendered":[]}
        return {"ok":True,"rendered":[str(pdf)],"bytes":pdf.stat().st_size,"renderer":"libreoffice"}

    def inspect_office_package(self,path,kind):
        p=Path(path)
        if kind not in {"word","excel","powerpoint"}: return {"ok":True}
        if not zipfile.is_zipfile(p): return {"ok":False,"reason":"not_office_package"}
        with zipfile.ZipFile(p) as z:
            names=set(z.namelist())
        core={"word":"word/document.xml","excel":"xl/workbook.xml","powerpoint":"ppt/presentation.xml"}[kind]
        return {"ok":core in names,"reason":None if core in names else "missing_core_part"}

    def inspect(self,path,kind):
        package=self.inspect_office_package(path,kind)
        if not package["ok"]: return package
        with tempfile.TemporaryDirectory() as d:
            rendered=self.render(path,d)
            if not rendered["ok"]: return rendered
            return {"ok":True,"kind":kind,"rendered_pdf":rendered["rendered"][0],
                    "rendered_bytes":rendered["bytes"],"renderer":rendered.get("renderer")}
