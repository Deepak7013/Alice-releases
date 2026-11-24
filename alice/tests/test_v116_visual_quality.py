from pathlib import Path
from alice.artifacts.visual_quality import VisualQualityAnalyzer
from reportlab.pdfgen import canvas

def _pdf(path, text="", pages=1):
    c=canvas.Canvas(str(path))
    for _ in range(pages):
        if text: c.drawString(72,720,text)
        c.showPage()
    c.save()

def test_visual_quality_detects_blank_page(tmp_path):
    p=tmp_path/"blank.pdf"; _pdf(p,"",1)
    r=VisualQualityAnalyzer().analyze_pdf(p)
    assert r["pages"]==1 and any("nearly_blank" in x for x in r["issues"])

def test_visual_quality_accepts_content_page(tmp_path):
    p=tmp_path/"content.pdf"; _pdf(p,"Alice creates a useful document with clear content.",1)
    r=VisualQualityAnalyzer().analyze_pdf(p)
    assert r["pages"]==1 and r["score"]>0

def test_visual_quality_reports_page_details(tmp_path):
    p=tmp_path/"multi.pdf"; _pdf(p,"Alice",2)
    r=VisualQualityAnalyzer().analyze_pdf(p)
    assert len(r["pages_detail"])==2

def test_compare_returns_winner(tmp_path):
    a=tmp_path/"a.pdf"; b=tmp_path/"b.pdf"
    _pdf(a,"Alice",1); _pdf(b,"",1)
    r=VisualQualityAnalyzer().compare(a,b)
    assert r["winner"]=="a"
