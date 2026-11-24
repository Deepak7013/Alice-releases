"""Provider-backed multimodal artifact expert.

Uses Alice's existing multi-provider Router. The expert is advisory only and
cannot execute actions, grant permissions, or mutate files.
"""
from __future__ import annotations
import json, re, tempfile
from pathlib import Path
import fitz

class MultimodalArtifactExpert:
    def __init__(self, router=None, max_pages=4):
        if router is None:
            from alice.providers.router import Router
            router=Router()
        self.router=router; self.max_pages=max(1,int(max_pages))

    def _render_pages(self,pdf_path):
        doc=fitz.open(pdf_path)
        paths=[]; tmp=tempfile.TemporaryDirectory()
        root=Path(tmp.name)
        for i,page in enumerate(doc):
            if i>=self.max_pages: break
            pix=page.get_pixmap(matrix=fitz.Matrix(1.2,1.2),alpha=False)
            p=root/f"page_{i+1}.png"; pix.save(str(p)); paths.append(p)
        doc.close()
        return tmp,paths

    @staticmethod
    def _parse(text):
        m=re.search(r"\{.*\}",text,re.S)
        if not m: raise ValueError("expert did not return JSON")
        data=json.loads(m.group(0))
        score=float(data.get("score",0.0)); conf=float(data.get("confidence",0.0))
        return {"score":max(0,min(1,score)),"confidence":max(0,min(1,conf)),
                "reasons":[str(x) for x in data.get("reasons",[])][:20]}

    def judge_pdf(self,pdf_path,context=None):
        tmp,paths=self._render_pages(pdf_path)
        try:
            results=[]
            prompt=("You are Alice's document design reviewer. Evaluate ONLY visible design/layout quality: "
                    "hierarchy, readability, spacing, alignment, density, consistency, visual balance and clarity. "
                    "Do not judge factual correctness. Return ONLY JSON with score 0..1, confidence 0..1, reasons array. "
                    f"Context: {context or {}}")
            for p in paths:
                raw=self.router.ask(prompt,image_path=str(p),allow_fallback=True)
                results.append(self._parse(raw))
            if not results: raise ValueError("no rendered pages")
            score=sum(x["score"] for x in results)/len(results)
            conf=sum(x["confidence"] for x in results)/len(results)
            reasons=[]
            for x in results: reasons.extend(x["reasons"])
            return {"score":round(score,4),"confidence":round(conf,4),"reasons":reasons[:30],"pages":len(results),"source":"multimodal_provider"}
        finally:
            tmp.cleanup()
