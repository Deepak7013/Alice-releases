
"""Deterministic rendered-artifact quality signals."""
from __future__ import annotations
from pathlib import Path
import zipfile, re

class ArtifactQualityScorer:
    """Scores structural/render signals; never claims human aesthetic judgment."""
    def score(self,path,kind,visual=None):
        p=Path(path); checks={}
        checks["exists"]=p.exists() and p.stat().st_size>0
        if kind in {"word","excel","powerpoint"}:
            checks["office_package"]=zipfile.is_zipfile(p)
        else:
            checks["office_package"]=True
        if visual:
            checks["rendered"]=bool(visual.get("ok"))
            checks["render_nonempty"]=int(visual.get("rendered_bytes",0))>0
        else:
            checks["rendered"]=None; checks["render_nonempty"]=None
        known=[v for v in checks.values() if v is not None]
        score=sum(bool(v) for v in known)/len(known) if known else 0.0
        return {"score":round(score,3),"checks":checks,
                "human_aesthetic_review":False,
                "limitations":["Does not judge taste, originality, or semantic correctness."]}

    def acceptable(self,result,threshold=.75):
        return bool(result.get("score",0)>=threshold and
                    result.get("checks",{}).get("exists",False))
