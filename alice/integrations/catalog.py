"""Unified inventory of Alice's integration surfaces.

This is intentionally a capability catalog rather than fake credentials. Each
entry states whether Alice ships an adapter locally and whether external auth is
required. Providers can be added without changing the brain or memory layers.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import json

@dataclass
class Integration:
    name: str
    category: str
    adapter: str
    available: bool
    requires_auth: bool = False
    description: str = ""

class IntegrationCatalog:
    def __init__(self, root=None):
        self.root=Path(root or Path(__file__).resolve().parents[2])
        self.path=self.root/"alice_workspace"/"integrations.json"
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.items=self._seed()
        self._save()

    def _seed(self):
        return [
            Integration("OpenRouter","AI","providers.router",True,True,"Primary multi-model brain and fallback routing."),
            Integration("Windows","Desktop","computer.windows",True,False,"Local applications, files and window control."),
            Integration("Browser","Web","browser.playwright_browser",True,False,"Controlled browser automation."),
            Integration("Web research","Web","research.web_research",True,False,"Public web search/fetch workflow."),
            Integration("Android/ADB","Mobile","android",True,True,"Android device control when ADB is authorized."),
            Integration("Voice/TTS","Audio","voice.voice",True,False,"Installed Windows voices; licensed external providers can be added."),
            Integration("Email","Productivity","email",True,True,"Email service surface; provider authentication is required."),
            Integration("Calendar","Productivity","calendar",True,True,"Calendar service surface; provider authentication is required."),
            Integration("WhatsApp","Messaging","messaging.whatsapp",True,True,"Messaging surface; requires authorized account/session."),
            Integration("Office artifacts","Documents","artifacts",True,False,"DOCX/XLSX/PPTX/PDF generation and QA."),
            Integration("GitHub","Developer","external.github",False,True,"Reserved adapter slot for an authorized GitHub integration."),
            Integration("Slack","Collaboration","external.slack",False,True,"Reserved adapter slot for an authorized Slack integration."),
            Integration("Google Drive","Storage","external.google_drive",False,True,"Reserved adapter slot for an authorized Drive integration."),
        ]

    def _save(self):
        self.path.write_text(json.dumps([asdict(x) for x in self.items],indent=2,ensure_ascii=False),encoding="utf-8")

    def list(self):
        return [asdict(x) for x in self.items]

    def get(self,name):
        target=str(name).strip().lower()
        for item in self.items:
            if item.name.lower()==target:
                return asdict(item)
        return None

    def summary(self):
        return {"total":len(self.items),"available":sum(x.available for x in self.items),"requires_auth":sum(x.requires_auth for x in self.items)}
