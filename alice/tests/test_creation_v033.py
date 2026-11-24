import tempfile
from pathlib import Path
from alice.creation import CreationService, CreationRequest, ArtifactKind

class FakeRouter:
    def ask(self, prompt): return "# Generated\n\nAlice created this artifact."

class FakeBuilder:
    def build_ai_agent(self, request, project_name, research=True):
        p=Path(tempfile.gettempdir())/project_name; p.mkdir(exist_ok=True)
        return {'ok':True,'project':str(p),'tests':{'ok':True}}
    def build(self, request, project_name, research=True):
        p=Path(tempfile.gettempdir())/project_name; p.mkdir(exist_ok=True)
        return {'ok':True,'project':str(p),'tests':{'ok':True}}

class FakeImage:
    def generate(self,prompt,output_path,size='1024x1024'):
        Path(output_path).write_bytes(b'PNG-TEST')
        return output_path

def test_text_markdown_code_creation(tmp_path):
    s=CreationService(router=FakeRouter(),root=tmp_path)
    for kind,ext in [(ArtifactKind.TEXT,'.txt'),(ArtifactKind.MARKDOWN,'.md'),(ArtifactKind.CODE,'.py')]:
        a=s.create(CreationRequest('make something',kind,filename='x'+ext))
        assert Path(a.path).exists()

def test_diagram_is_editable_svg(tmp_path):
    s=CreationService(root=tmp_path)
    a=s.create(CreationRequest('User -> Planner -> Executor -> Verify',ArtifactKind.DIAGRAM,filename='flow.svg'))
    text=Path(a.path).read_text()
    assert text.startswith('<svg') and 'Planner' in text and 'marker-end' in text

def test_image_adapter_is_used_without_credentials_in_core(tmp_path):
    s=CreationService(image_provider=FakeImage(),root=tmp_path)
    a=s.create(CreationRequest('a futuristic AI lab',ArtifactKind.IMAGE,filename='lab.png'))
    assert Path(a.path).read_bytes()==b'PNG-TEST'

def test_ai_agent_creation_uses_existing_builder(tmp_path):
    s=CreationService(builder=FakeBuilder(),root=tmp_path)
    a=s.create(CreationRequest('build a study assistant',ArtifactKind.AI_AGENT,project_name='study-agent'))
    assert a.kind==ArtifactKind.AI_AGENT and Path(a.path).exists()
