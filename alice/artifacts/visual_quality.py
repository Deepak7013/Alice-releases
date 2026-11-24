"""Multimodal visual heuristics for rendered Office artifacts.

This is an objective visual-quality layer: it inspects rendered pages/images
for blankness, occupancy, text density, contrast and page consistency. It does
not claim human taste or semantic correctness.
"""
from __future__ import annotations
from pathlib import Path
import math, tempfile
import fitz
from PIL import Image, ImageStat

class VisualQualityAnalyzer:
    def __init__(self, dpi=72):
        self.dpi=int(dpi)

    def analyze_pdf(self, pdf_path):
        p=Path(pdf_path)
        doc=fitz.open(p)
        pages=[]
        for page in doc:
            rect=page.rect
            pix=page.get_pixmap(matrix=fitz.Matrix(self.dpi/72,self.dpi/72), alpha=False)
            img=Image.frombytes("RGB",[pix.width,pix.height],pix.samples)
            stat=ImageStat.Stat(img)
            # Count non-white pixels approximately; threshold avoids anti-alias noise.
            gray=img.convert("L")
            hist=gray.histogram()
            total=img.width*img.height
            near_white=sum(hist[245:256])
            occupancy=1.0-near_white/max(1,total)
            text=" ".join(block[4] for block in page.get_text("blocks") if len(block)>4)
            text_chars=len(text.strip())
            images=len(page.get_images(full=True))
            mean=sum(stat.mean)/3.0
            std=sum(stat.stddev)/3.0
            pages.append({
                "width":img.width,"height":img.height,
                "occupancy":round(occupancy,4),
                "text_chars":text_chars,"images":images,
                "mean_luminance":round(mean,2),"contrast_std":round(std,2),
            })
        doc.close()
        if not pages:
            return {"score":0.0,"pages":0,"issues":["empty_document"],"pages_detail":[]}
        issues=[]
        for i,x in enumerate(pages,1):
            if x["occupancy"] < .015: issues.append(f"page_{i}_nearly_blank")
            if x["text_chars"] > 9000: issues.append(f"page_{i}_text_dense")
            if x["contrast_std"] < 5 and x["occupancy"] > .02: issues.append(f"page_{i}_low_visual_contrast")
        occup=[x["occupancy"] for x in pages]
        # Penalize extreme blankness and extreme density, reward consistent page occupancy.
        blank_score=sum(1 for x in pages if x["occupancy"]>=.015)/len(pages)
        density_score=sum(1 for x in pages if x["text_chars"]<=9000)/len(pages)
        mean_occ=sum(occup)/len(occup)
        occupancy_score=min(1.0,max(0.0,mean_occ/.12)) if mean_occ else 0.0
        consistency=1.0-(max(occup)-min(occup)) if len(occup)>1 else 1.0
        score=0.35*blank_score+0.25*density_score+0.25*occupancy_score+0.15*max(0,consistency)
        return {"score":round(score,4),"pages":len(pages),"issues":issues,
                "pages_detail":pages,
                "human_aesthetic_review":False,
                "limitations":["Heuristics cannot judge taste, originality, factual correctness, or whether a layout communicates the intended message."]}

    def compare(self, pdf_a, pdf_b):
        a=self.analyze_pdf(pdf_a); b=self.analyze_pdf(pdf_b)
        if a["score"]>b["score"]: winner="a"
        elif b["score"]>a["score"]: winner="b"
        else: winner="tie"
        return {"winner":winner,"a_score":a["score"],"b_score":b["score"]}
