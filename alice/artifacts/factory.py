"""Alice Artifact Factory: native document creation with deterministic local output."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json, hashlib, time, re

@dataclass
class ArtifactResult:
    path: str
    kind: str
    title: str
    sha256: str
    bytes: int

class ArtifactFactory:
    EXTENSIONS={"word":".docx","excel":".xlsx","powerpoint":".pptx","pdf":".pdf","markdown":".md","text":".txt"}
    def __init__(self, root=None):
        self.root=Path(root or Path(__file__).resolve().parents[2])/"alice_workspace"/"artifacts"
        self.root.mkdir(parents=True,exist_ok=True)
    def _target(self, kind,title):
        kind=kind.lower().strip()
        if kind not in self.EXTENSIONS: raise ValueError(f"Unsupported artifact kind: {kind}")
        safe=re.sub(r"[^A-Za-z0-9._-]+","_",title.strip()).strip("._") or "artifact"
        return self.root/(safe+self.EXTENSIONS[kind])
    def create_word(self,title,sections):
        from docx import Document
        from docx.shared import Pt
        p=self._target("word",title); d=Document()
        d.add_heading(title,0)
        for s in sections:
            if isinstance(s,dict) and s.get("heading"): d.add_heading(s["heading"],level=min(3,max(1,int(s.get("level",1))))
            )
            body=s.get("body","") if isinstance(s,dict) else str(s)
            for para in str(body).split("\n"):
                d.add_paragraph(para)
        d.save(p); return self._result(p,"word",title)
    def create_excel(self,title,sheets):
        from openpyxl import Workbook
        p=self._target("excel",title); wb=Workbook(); wb.remove(wb.active)
        for name,rows in sheets.items():
            ws=wb.create_sheet(str(name)[:31] or "Sheet")
            for row in rows:
                ws.append(list(row) if not isinstance(row,dict) else list(row.values()))
            if ws.max_row and ws.max_column:
                ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions
        wb.save(p); return self._result(p,"excel",title)
    def create_powerpoint(self,title,slides):
        from pptx import Presentation
        from pptx.util import Inches
        prs=Presentation()
        for i,s in enumerate(slides):
            layout=prs.slide_layouts[0] if i==0 else prs.slide_layouts[1]
            slide=prs.slides.add_slide(layout)
            slide.shapes.title.text=str(s.get("title",title))
            if i==0 and "body" in s: slide.placeholders[1].text=str(s["body"])
            elif "body" in s: slide.placeholders[1].text=str(s["body"])
        p=self._target("powerpoint",title); prs.save(p); return self._result(p,"powerpoint",title)
    def create_pdf(self,title,sections):
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        p=self._target("pdf",title); styles=getSampleStyleSheet(); story=[Paragraph(title,styles["Title"]),Spacer(1,12)]
        for s in sections:
            if isinstance(s,dict) and s.get("heading"): story.append(Paragraph(str(s["heading"]),styles["Heading2"]))
            story.append(Paragraph(str(s.get("body","") if isinstance(s,dict) else s).replace("&","&amp;"),styles["BodyText"]))
            story.append(Spacer(1,8))
        SimpleDocTemplate(str(p)).build(story); return self._result(p,"pdf",title)
    def create_text(self,title,content,kind="text"):
        p=self._target(kind,title); p.write_text(str(content),encoding="utf-8"); return self._result(p,kind,title)
    def _result(self,p,kind,title):
        b=p.read_bytes()
        return ArtifactResult(str(p),kind,title,hashlib.sha256(b).hexdigest(),len(b))

    def create_styled_word(self,title,sections,style="alice_clean",custom=None):
        from docx import Document
        from docx.shared import Pt
        from .styles import resolve_style
        st=resolve_style(style,custom); p=self._target("word",title); d=Document()
        normal=d.styles["Normal"]; normal.font.name=st.font; normal.font.size=Pt(st.body_size)
        d.add_heading(title,0)
        for sec in sections:
            if isinstance(sec,dict) and sec.get("heading"): d.add_heading(str(sec["heading"]),level=min(3,max(1,int(sec.get("level",1)))))
            body=sec.get("body","") if isinstance(sec,dict) else str(sec)
            for para in str(body).split("\n"): d.add_paragraph(para)
        d.save(p); return self._result(p,"word",title)
    def create_styled_excel(self,title,sheets,style="alice_clean",custom=None):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from .styles import resolve_style
        st=resolve_style(style,custom); p=self._target("excel",title); wb=Workbook(); wb.remove(wb.active)
        for name,rows in sheets.items():
            ws=wb.create_sheet(str(name)[:31] or "Sheet")
            for row in rows: ws.append(list(row))
            if ws.max_row and ws.max_column:
                ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions
                for c in ws[1]:
                    c.font=Font(name=st.font,bold=True,color="FFFFFF")
                    c.fill=PatternFill("solid",fgColor=st.accent)
                    c.alignment=Alignment(horizontal="center")
        wb.save(p); return self._result(p,"excel",title)


    def create_reference_powerpoint(self,title,slides,style="alice_clean"):
        """Create a content-driven deck using proven Office layout patterns."""
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from .reference_design import classify_slide, choose_theme, style_metadata
        from .styles import resolve_style
        st=resolve_style(style)
        theme=choose_theme(style)
        p=self._target("powerpoint",title)
        prs=Presentation()
        prs.slide_width=Inches(13.333)
        prs.slide_height=Inches(7.5)
        items=list(slides or [{"title":title,"body":""}])
        for i,s in enumerate(items):
            s=dict(s) if isinstance(s,dict) else {"title":str(s)}
            layout=classify_slide(s,i,len(items))
            blank=prs.slide_layouts[6]
            slide=prs.slides.add_slide(blank)
            # consistent background
            bg=slide.background.fill
            bg.solid(); bg.fore_color.rgb=RGBColor.from_string("F7F9FC")
            # title
            tb=slide.shapes.add_textbox(Inches(.65),Inches(.42),Inches(12.0),Inches(.7))
            tf=tb.text_frame; tf.clear()
            para=tf.paragraphs[0]; para.text=str(s.get("title",title))
            para.font.name=st.font; para.font.size=Pt(max(26,st.title_size)); para.font.bold=True
            para.font.color.rgb=RGBColor.from_string(theme.dark)
            # accent line
            line=slide.shapes.add_shape(1, Inches(.65), Inches(1.18), Inches(1.0), Inches(.07))
            line.fill.solid(); line.fill.fore_color.rgb=RGBColor.from_string(theme.accent); line.line.fill.background()
            if layout=="two_column":
                for key,x in (("left",.75),("right",6.85)):
                    box=slide.shapes.add_textbox(Inches(x),Inches(1.55),Inches(5.7),Inches(4.9))
                    t=box.text_frame; t.word_wrap=True; t.text=str(s.get(key,s.get("body","")))
                    for para in t.paragraphs:
                        para.font.name=st.font; para.font.size=Pt(max(18,st.body_size+8))
                        para.font.color.rgb=RGBColor.from_string(theme.dark)
            elif layout=="metrics":
                vals=s.get("metrics",[])
                if not isinstance(vals,list): vals=[vals]
                for j,m in enumerate(vals[:4]):
                    x=.75+j*3.05
                    box=slide.shapes.add_textbox(Inches(x),Inches(2.0),Inches(2.6),Inches(2.2))
                    t=box.text_frame; t.clear()
                    p1=t.paragraphs[0]; p1.text=str(m.get("value",m) if isinstance(m,dict) else m)
                    p1.font.name=st.font; p1.font.size=Pt(30); p1.font.bold=True
                    p2=t.add_paragraph(); p2.text=str(m.get("label","") if isinstance(m,dict) else "")
                    p2.font.name=st.font; p2.font.size=Pt(18)
            elif layout=="timeline":
                steps=s.get("steps",s.get("body",""))
                if not isinstance(steps,list): steps=[steps]
                for j,step in enumerate(steps[:6]):
                    x=.8+j*2.05
                    circ=slide.shapes.add_shape(9,Inches(x),Inches(2.0),Inches(.62),Inches(.62))
                    circ.fill.solid(); circ.fill.fore_color.rgb=RGBColor.from_string(theme.accent); circ.line.fill.background()
                    box=slide.shapes.add_textbox(Inches(x-.15),Inches(2.75),Inches(1.8),Inches(2.0))
                    t=box.text_frame; t.word_wrap=True; t.text=str(step)
                    for para in t.paragraphs:
                        para.font.name=st.font; para.font.size=Pt(18)
            else:
                box=slide.shapes.add_textbox(Inches(.85),Inches(1.65),Inches(11.7),Inches(4.8))
                t=box.text_frame; t.word_wrap=True
                body=s.get("body","")
                if isinstance(body,list):
                    t.clear()
                    for j,item in enumerate(body):
                        p0=t.paragraphs[0] if j==0 else t.add_paragraph()
                        p0.text=str(item); p0.font.name=st.font; p0.font.size=Pt(max(18,st.body_size+8))
                else:
                    t.text=str(body)
                    for para in t.paragraphs:
                        para.font.name=st.font; para.font.size=Pt(max(18,st.body_size+8))
            # small footer mark
            foot=slide.shapes.add_textbox(Inches(.65),Inches(7.08),Inches(12),Inches(.22))
            foot.text_frame.text=f"Alice • {i+1}/{len(items)}"
            for para in foot.text_frame.paragraphs:
                para.font.name=st.font; para.font.size=Pt(9); para.font.color.rgb=RGBColor.from_string("6B7280")
        prs.save(p)
        return self._result(p,"powerpoint",title)


    def create_reference_word(self,title,sections,style="alice_clean"):
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from .reference_design import choose_theme
        from .styles import resolve_style
        st=resolve_style(style); theme=choose_theme(style)
        p=self._target("word",title); d=Document()
        sec=d.sections[0]
        sec.top_margin=Inches(.7); sec.bottom_margin=Inches(.7)
        sec.left_margin=Inches(.8); sec.right_margin=Inches(.8)
        normal=d.styles["Normal"]; normal.font.name=st.font; normal.font.size=Pt(st.body_size)
        normal.paragraph_format.space_after=Pt(7)
        title_p=d.add_paragraph(); title_p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        r=title_p.add_run(title); r.font.name=st.font; r.font.size=Pt(30); r.bold=True
        sub=d.add_paragraph("Prepared by Alice"); sub.alignment=WD_ALIGN_PARAGRAPH.CENTER
        for secdata in sections:
            if isinstance(secdata,dict) and secdata.get("heading"):
                h=d.add_heading(str(secdata["heading"]),level=min(2,max(1,int(secdata.get("level",1)))))
                for run in h.runs:
                    run.font.name=st.font; run.font.color.rgb=__import__("docx").shared.RGBColor.from_string(theme.accent)
            body=secdata.get("body","") if isinstance(secdata,dict) else str(secdata)
            for para in str(body).split("\n"):
                d.add_paragraph(para)
        footer=d.sections[0].footer.paragraphs[0]; footer.text="Alice • Reference Office Layout"
        d.save(p); return self._result(p,"word",title)

    def create_reference_excel(self,title,sheets,style="alice_clean"):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.worksheet.table import Table, TableStyleInfo
        from openpyxl.worksheet.page import PageMargins
        from .reference_design import choose_theme
        from .styles import resolve_style
        st=resolve_style(style); theme=choose_theme(style)
        p=self._target("excel",title); wb=Workbook(); wb.remove(wb.active)
        for name,rows in sheets.items():
            ws=wb.create_sheet(str(name)[:31] or "Sheet")
            rows=list(rows or [])
            for row in rows: ws.append(list(row) if not isinstance(row,dict) else list(row.values()))
            if ws.max_row and ws.max_column:
                ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions
                ws.sheet_view.showGridLines=False
                ws.page_setup.orientation="landscape"; ws.page_setup.fitToWidth=1; ws.sheet_properties.pageSetUpPr.fitToPage=True
                ws.page_margins=PageMargins(left=.25,right=.25,top=.5,bottom=.5)
                for c in ws[1]:
                    c.font=Font(name=st.font,bold=True,color="FFFFFF",size=11)
                    c.fill=PatternFill("solid",fgColor=theme.accent)
                    c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
                for col in ws.columns:
                    letter=col[0].column_letter
                    width=min(max(max(len(str(c.value or "")) for c in col)+2,10),32)
                    ws.column_dimensions[letter].width=width
                ref=f"A1:{ws.cell(ws.max_row,ws.max_column).coordinate}"
                tab=Table(displayName="T"+str(abs(hash(str(name)))%1000000),ref=ref)
                tab.tableStyleInfo=TableStyleInfo(name="TableStyleMedium2",showRowStripes=True,showColumnStripes=False)
                ws.add_table(tab)
        wb.save(p); return self._result(p,"excel",title)
