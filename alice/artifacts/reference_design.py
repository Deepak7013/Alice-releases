"""Reference-based Office design engine.

Design principles are derived from established Microsoft Office template/Designer
patterns: coherent themes, purposeful layouts, readable typography, contrast,
consistent spacing, and content-driven slide composition. No proprietary assets
are bundled.
"""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ReferenceTheme:
    name: str
    font: str
    accent: str
    dark: str
    light: str
    body_size: int
    slide_min_size: int = 18

MICROSOFT_INSPIRED = ReferenceTheme(
    "office_reference", "Aptos", "2F5597", "1F2937", "F7F9FC", 11, 18
)

LAYOUTS = {
    "title": {"purpose":"opening", "slots":["title","subtitle"]},
    "section": {"purpose":"section_break", "slots":["title","subtitle"]},
    "two_column": {"purpose":"comparison_or_explanation", "slots":["title","left","right"]},
    "metrics": {"purpose":"kpis", "slots":["title","metrics"]},
    "timeline": {"purpose":"process_or_schedule", "slots":["title","steps"]},
    "content": {"purpose":"single_message", "slots":["title","body"]},
    "closing": {"purpose":"conclusion", "slots":["title","body"]},
}

def classify_slide(slide: dict, index: int, total: int) -> str:
    if index == 0:
        return "title"
    if index == total - 1 and total > 2:
        return "closing"
    text = str(slide.get("body","")).lower()
    if any(k in text for k in ("timeline","roadmap","phase","step 1","step 2")):
        return "timeline"
    if any(k in text for k in ("kpi","metric","revenue","growth","percentage","%")):
        return "metrics"
    if isinstance(slide.get("left"), (str,list,dict)) or isinstance(slide.get("right"), (str,list,dict)):
        return "two_column"
    return "content"

def choose_theme(style=None):
    # Alice's own named styles may override the reference theme later.
    return MICROSOFT_INSPIRED

def style_metadata(style=None):
    theme = choose_theme(style)
    return {
        "reference": "Microsoft Office template/Designer principles",
        "theme": theme.name,
        "font": theme.font,
        "accent": theme.accent,
        "readability_min_slide_pt": theme.slide_min_size,
        "layout_policy": "content_driven",
        "proprietary_assets": False,
    }
