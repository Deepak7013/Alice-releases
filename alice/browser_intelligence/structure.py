
from __future__ import annotations
from .models import BrowserPageState, BrowserElement, FormField

class StructureAnalyzer:
    def from_snapshot(self, url: str, title: str, nodes: list[dict]) -> BrowserPageState:
        elements=[]
        forms=[]
        useful=0
        for n in nodes:
            role=str(n.get("role","")).lower()
            name=str(n.get("name","") or "")
            selector=n.get("selector")
            visible=bool(n.get("visible", True))
            enabled=bool(n.get("enabled", True))
            if role or name:
                useful += 1
            elements.append(BrowserElement(role,name,selector,n.get("value"),visible,enabled,n))
            if role in {"textbox","searchbox","combobox","checkbox","radio"}:
                forms.append(FormField(name or n.get("placeholder",""), role, selector,
                                       bool(n.get("required",False)), n.get("value")))
        quality=min(1.0, useful/max(1,len(nodes)))
        logged=self.infer_login(elements)
        return BrowserPageState(url,title,elements,forms,logged,quality)

    def infer_login(self, elements):
        names=" ".join((e.name or "").casefold() for e in elements)
        if any(x in names for x in ("log out","logout","sign out","account","profile")):
            return True
        if any(x in names for x in ("log in","login","sign in")):
            return False
        return None
