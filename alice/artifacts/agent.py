
"""Unified artifact agent: choose format, reuse learned recipes, create, and verify."""
from __future__ import annotations
from .factory import ArtifactFactory
from .memory import ArtifactMemory
from .qa import ArtifactQA

class ArtifactAgent:
    KIND_ALIASES={
      "word":"word","doc":"word","document":"word","docx":"word",
      "excel":"excel","spreadsheet":"excel","xlsx":"excel","sheet":"excel",
      "powerpoint":"powerpoint","ppt":"powerpoint","pptx":"powerpoint","slides":"powerpoint",
      "pdf":"pdf","markdown":"markdown","md":"markdown","text":"text","txt":"text"
    }
    def __init__(self,root=None):
        self.factory=ArtifactFactory(root); self.memory=ArtifactMemory(root); self.qa=ArtifactQA()
    def normalize_kind(self,kind):
        k=self.KIND_ALIASES.get(str(kind).lower().strip())
        if not k: raise ValueError(f"Unsupported artifact kind: {kind}")
        return k
    def create(self, task, kind, title, content, *, style=None, remember=True):
        k=self.normalize_kind(kind)
        learned=self.memory.recall_best_recipe(task,k) if remember else None
        recipe=(learned or {}).get("recipe") if learned else None
        chosen_style=style or (recipe or {}).get("style") or "alice_clean"
        if k=="word": result=self.factory.create_reference_word(title,content,chosen_style)
        elif k=="excel": result=self.factory.create_reference_excel(title,content,chosen_style)
        elif k=="powerpoint": result=self.factory.create_reference_powerpoint(title,content,chosen_style)
        elif k=="pdf": result=self.factory.create_pdf(title,content)
        elif k in {"markdown","text"}: result=self.factory.create_text(title,content,k)
        else: raise ValueError(k)
        qa=self.qa.inspect(result.path,k)
        if not qa["ok"]: raise RuntimeError(f"Artifact verification failed: {qa['reason']}")
        if remember:
            learned_recipe={"style":chosen_style,"title":title,"layout":(recipe or {}).get("layout","reference")}
            self.memory.learn_outcome(task,k,learned_recipe,True,qa)
            self.memory.record(k,title,learned_recipe,True)
        return {
            "artifact":result,
            "verification":qa,
            "reused_recipe":recipe is not None,
            "recipe_source":(learned or {}).get("source") if learned else None,
            "recipe_similarity":(learned or {}).get("similarity") if learned else 0.0,
        }
