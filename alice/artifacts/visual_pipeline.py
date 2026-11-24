"""Rendered artifact pipeline with durable inspection results."""
from __future__ import annotations
from pathlib import Path
import hashlib, shutil, tempfile
from .visual_qa import VisualArtifactQA
from .visual_quality import VisualQualityAnalyzer

class VisualArtifactPipeline:
    def __init__(self, timeout=60, output_root=None):
        self.renderer=VisualArtifactQA(timeout)
        self.analyzer=VisualQualityAnalyzer()
        self.output_root=Path(output_root or (Path.cwd()/"alice_workspace"/"rendered_artifacts"))
        self.output_root.mkdir(parents=True,exist_ok=True)

    def inspect(self, path, kind):
        source=Path(path).resolve()
        package=self.renderer.inspect_office_package(source,kind)
        if not package.get("ok"):
            return {"ok":False,"reason":package.get("reason","invalid_package")}
        with tempfile.TemporaryDirectory() as d:
            rendered=self.renderer.render(source,d)
            if not rendered.get("ok"):
                return {"ok":False,"reason":rendered.get("reason","render_failed")}
            pdf=Path(rendered["rendered"][0])
            visual=self.analyzer.analyze_pdf(pdf)
            digest=hashlib.sha256(source.read_bytes()).hexdigest()[:20]
            durable=self.output_root/(f"{source.stem}_{digest}.pdf")
            shutil.copy2(pdf,durable)
            return {"ok":True,"rendered":{"ok":True,"rendered_pdf":str(durable),
                    "rendered_bytes":durable.stat().st_size,"renderer":rendered.get("renderer")},
                    "visual":visual,"quality_score":visual["score"]}
