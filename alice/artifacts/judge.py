"""Pluggable artifact judgment.

A configured expert callback may provide semantic/aesthetic judgment. Without
one, Alice falls back to deterministic visual heuristics and clearly labels
the limitation. The callback cannot grant permissions or execute actions.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any
from .visual_quality import VisualQualityAnalyzer

@dataclass
class Judgment:
    score: float
    visual_score: float
    expert_score: float|None
    confidence: float
    reasons: list
    source: str

class ArtifactJudge:
    def __init__(self, expert:Callable[[dict],dict]|None=None, provider_expert=None):
        self.expert=expert
        self.provider_expert=provider_expert
        self.visual=VisualQualityAnalyzer()

    def judge_pdf(self,pdf_path,context=None):
        visual=self.visual.analyze_pdf(pdf_path)
        vs=float(visual["score"])
        if not self.expert and self.provider_expert:
            try:
                raw=self.provider_expert.judge_pdf(pdf_path,context=context)
                es=max(0.0,min(1.0,float(raw.get("score",0))))
                conf=max(0.0,min(1.0,float(raw.get("confidence",0.5))))
                final=.45*vs+.55*es
                return Judgment(round(final,4),round(vs,4),round(es,4),round(conf,4),
                                list(visual["issues"])+list(raw.get("reasons",[])),"visual_plus_multimodal_provider")
            except Exception:
                pass
        if not self.expert:
            return Judgment(round(vs,4),round(vs,4),None,0.55,
                            list(visual["issues"]),
                            "deterministic_visual_heuristics")
        try:
            raw=self.expert({"context":context or {},"visual":visual})
            es=max(0.0,min(1.0,float(raw.get("score",0))))
            conf=max(0.0,min(1.0,float(raw.get("confidence",0.5))))
            final=.45*vs+.55*es
            reasons=list(visual["issues"])+list(raw.get("reasons",[]))
            return Judgment(round(final,4),round(vs,4),round(es,4),round(conf,4),
                            reasons,"visual_plus_expert")
        except Exception as exc:
            return Judgment(round(vs,4),round(vs,4),None,0.35,
                            list(visual["issues"])+["expert_failed"],
                            "visual_fallback")
