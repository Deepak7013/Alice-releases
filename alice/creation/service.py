from __future__ import annotations
import json, re
from pathlib import Path
from .models import Artifact, ArtifactKind, CreationRequest
from .diagram import FlowDiagramBuilder

class CreationService:
    """Unified safe artifact creation facade for Alice."""
    def __init__(self, router=None, builder=None, image_provider=None, root=None):
        self.router=router; self.builder=builder; self.image_provider=image_provider
        self.root=Path(root or Path.cwd()).resolve(); self.output=(self.root/'alice_workspace'/'artifacts').resolve(); self.output.mkdir(parents=True,exist_ok=True)
        self.diagrams=FlowDiagramBuilder()

    def _safe_name(self, name, default):
        name=re.sub(r'[^A-Za-z0-9_.-]+','-',str(name or '').strip()).strip('.-')[:100] or default
        return name

    def create(self, request: CreationRequest):
        if not isinstance(request, CreationRequest): raise TypeError('request must be CreationRequest')
        if not request.prompt.strip() or len(request.prompt)>20000: raise ValueError('Invalid creation prompt')
        kind=request.kind
        if kind in (ArtifactKind.TEXT, ArtifactKind.MARKDOWN, ArtifactKind.CODE):
            if not self.router: raise RuntimeError('Text router is not configured')
            ext='.md' if kind==ArtifactKind.MARKDOWN else ('.txt' if kind==ArtifactKind.TEXT else '.py')
            name=self._safe_name(request.filename, 'artifact'+ext)
            if '.' not in name: name += ext
            instruction=f"Create the requested {kind.value}. Return ONLY the artifact content, no surrounding explanation. User request: {request.prompt}\nStyle: {request.style}"
            content=self.router.ask(instruction)
            p=self.output/name; p.write_text(content,encoding='utf-8')
            return Artifact(kind,str(p),'Created by Alice text generation',{'style':request.style})
        if kind==ArtifactKind.DIAGRAM:
            name=self._safe_name(request.filename,'flow.svg')
            if not name.lower().endswith('.svg'): name += '.svg'
            p=self.output/name
            self.diagrams.from_text(request.prompt,p,request.context.get('title','Flow Diagram'))
            return Artifact(kind,str(p),'Created as a deterministic SVG flow diagram',{'editable':True})
        if kind==ArtifactKind.IMAGE:
            if not self.image_provider: raise RuntimeError('No image generation provider configured')
            name=self._safe_name(request.filename,'image.png')
            if '.' not in name: name += '.png'
            p=self.output/name
            self.image_provider.generate(request.prompt,p,request.context.get('size','1024x1024'))
            return Artifact(kind,str(p),'Created with the configured image provider',{'provider':type(self.image_provider).__name__})
        if kind==ArtifactKind.AI_AGENT:
            if not self.builder: raise RuntimeError('Builder is not configured')
            result=self.builder.build_ai_agent(request.prompt, project_name=request.project_name or 'alice-created-agent', research=True)
            if not result.get('ok'): raise RuntimeError('AI agent build failed: '+str(result))
            return Artifact(kind,str(result['project']),'Created a tested AI agent project',result)
        if kind==ArtifactKind.PROJECT:
            if not self.builder: raise RuntimeError('Builder is not configured')
            result=self.builder.build(request.prompt, project_name=request.project_name or 'alice-created-project', research=True)
            if not result.get('ok'): raise RuntimeError('Project build failed: '+str(result))
            return Artifact(kind,str(result['project']),'Created a tested software project',result)
        raise ValueError('Unsupported artifact kind')
