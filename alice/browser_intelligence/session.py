
from __future__ import annotations
from .models import BrowserTab
from .structure import StructureAnalyzer

class BrowserIntelligenceSession:
    """Semantic browser layer over a Playwright-like backend.

    The backend is injected so the intelligence layer can be tested without
    launching a real browser and can later support multiple browser engines.
    """
    def __init__(self, backend, vision_fallback=None, min_structure_quality=0.45):
        self.backend=backend
        self.vision_fallback=vision_fallback
        self.min_structure_quality=min_structure_quality
        self.analyzer=StructureAnalyzer()

    def tabs(self):
        return [BrowserTab(**t) for t in self.backend.tabs()]

    def open_tab(self, url):
        return self.backend.open_tab(url)

    def close_tab(self, tab_id):
        return self.backend.close_tab(tab_id)

    def activate_tab(self, tab_id):
        return self.backend.activate_tab(tab_id)

    def observe(self):
        snap=self.backend.accessibility_snapshot()
        state=self.analyzer.from_snapshot(
            self.backend.url(), self.backend.title(), snap or []
        )
        if state.structure_quality < self.min_structure_quality and self.vision_fallback:
            visual=self.vision_fallback(self.backend.screenshot(), "understand webpage controls")
            state.metadata["visual_fallback"]=visual
        return state

    def click(self, name, role=None):
        state=self.observe()
        candidates=[e for e in state.elements
                    if e.visible and e.enabled and e.name.casefold()==name.casefold()
                    and (role is None or e.role==role)]
        if candidates:
            e=candidates[0]
            return self.backend.click(selector=e.selector, role=e.role, name=e.name)
        if self.vision_fallback:
            return self.backend.visual_click(name, role)
        return False

    def fill_form(self, values: dict[str,str]):
        state=self.observe()
        results={}
        for label,value in values.items():
            field=next((f for f in state.forms if f.label.casefold()==label.casefold()),None)
            results[label]=bool(field and self.backend.fill(field.selector,value))
        return results

    def upload(self, selector, path):
        return self.backend.upload(selector,path)

    def downloads(self):
        return self.backend.downloads()
