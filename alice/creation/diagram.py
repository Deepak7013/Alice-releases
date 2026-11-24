from __future__ import annotations
from pathlib import Path
import html
import re

class FlowDiagramBuilder:
    """Create safe, deterministic SVG flow diagrams without requiring an image model."""

    def _nodes(self, steps):
        out=[]
        for i, step in enumerate(steps):
            label = re.sub(r"\s+", " ", str(step).strip())[:80] or f"Step {i+1}"
            out.append((i, label))
        return out

    def svg(self, title, steps, output_path):
        nodes=self._nodes(steps)
        if not nodes: raise ValueError("At least one diagram step is required")
        width=720; box_w=500; box_h=64; gap=42; left=110; top=80
        height=top + len(nodes)*(box_h+gap) + 30
        esc=lambda s: html.escape(str(s))
        parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
               '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#333"/></marker></defs>',
               '<rect width="100%" height="100%" fill="white"/>', f'<text x="{width/2}" y="42" text-anchor="middle" font-size="24" font-family="Arial" font-weight="700">{esc(title)}</text>']
        for i, label in nodes:
            y=top+i*(box_h+gap)
            parts.append(f'<rect x="{left}" y="{y}" width="{box_w}" height="{box_h}" rx="12" fill="#eef4ff" stroke="#3b5ccc" stroke-width="2"/>')
            parts.append(f'<text x="{width/2}" y="{y+39}" text-anchor="middle" font-size="17" font-family="Arial">{esc(label)}</text>')
            if i < len(nodes)-1:
                y2=y+box_h
                parts.append(f'<line x1="{width/2}" y1="{y2}" x2="{width/2}" y2="{y+box_h+gap-8}" stroke="#333" stroke-width="2" marker-end="url(#arrow)"/>')
        parts.append('</svg>')
        p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("\n".join(parts),encoding="utf-8")
        return str(p)

    def from_text(self, text, output_path, title="Flow Diagram"):
        steps=[x.strip(" -•\t") for x in re.split(r"\n|->|=>|→", str(text)) if x.strip()]
        return self.svg(title, steps[:12], output_path)
