
import json
from alice.capabilities.skills import SkillForge

class FakeRouter:
    def __init__(self, raw): self.raw=raw
    def ask(self, prompt, image_path=None): return self.raw

def test_skillforge_rejects_network_and_shell_imports(tmp_path):
    forge=SkillForge(FakeRouter("{}"), root=tmp_path)
    for source in (
        "import subprocess\n\ndef run(**kwargs): return 1\n",
        "import socket\n\ndef run(**kwargs): return 1\n",
        "import os\n\ndef run(**kwargs): return 1\n",
    ):
        try:
            forge._validate(source)
        except ValueError:
            pass
        else:
            assert False

def test_skillforge_accepts_pure_skill(tmp_path):
    payload=json.dumps({
        "name":"sum_values",
        "description":"Sum numbers",
        "code":"def run(**kwargs):\n    return sum(kwargs.get('values', []))\n",
        "tests":["sum values correctly"],
    })
    forge=SkillForge(FakeRouter(payload), root=tmp_path)
    result=forge.learn("sum values","aggregation")
    assert result["ok"]
    assert (tmp_path/"alice_workspace"/"skills"/"sum_values.py").exists()
    assert result["tests"]["smoke"]["ok"]

def test_skillforge_never_executes_test_shell_commands(tmp_path):
    payload=json.dumps({
        "name":"safe_skill",
        "description":"safe",
        "code":"def run(**kwargs): return True\n",
        "tests":["python -c \"raise SystemExit(99)\""],
    })
    forge=SkillForge(FakeRouter(payload), root=tmp_path)
    result=forge.learn("safe","safe")
    assert result["ok"]
    assert result["tests"]["descriptions"][0].startswith("python -c")
