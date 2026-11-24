from pathlib import Path
import importlib.util

ROOT=Path("skills")
def discover():
    ROOT.mkdir(exist_ok=True)
    return [p for p in ROOT.glob("*/skill.py") if p.is_file()]

def load(path):
    spec=importlib.util.spec_from_file_location("alice_external_skill",path)
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod
