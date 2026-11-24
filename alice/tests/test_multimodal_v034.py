from pathlib import Path
from alice.multimodal import MultimodalAnalyzer, MediaKind, classify

class FakeVisionResult:
    ok=True; provider='fake-vision'; text='''{"summary":"A flow diagram","extracted_text":"Start Planner Verify","elements":[{"label":"Planner","kind":"box","confidence":0.98,"bounds":[1,2,3,4],"text":"Planner"}],"claims":["The diagram has a planner"],"warnings":[]}'''
class FakeVision:
    def analyze(self,image,prompt): return FakeVisionResult()
class FakeRouter:
    def ask(self,prompt,image_path=None): return '{"summary":"A short document","claims":["It contains a workflow"],"warnings":[]}'

def test_classify_and_hash(tmp_path):
    p=tmp_path/'a.txt'; p.write_text('hello')
    assert classify(str(p))[0]=='document'
    assert len(__import__('alice.multimodal',fromlist=['digest']).digest(str(p)))==64

def test_image_understanding_is_structured_and_untrusted(tmp_path):
    p=tmp_path/'x.png'; p.write_bytes(b'fake')
    a=MultimodalAnalyzer(vision_router=FakeVision())
    o=a.analyze_image(str(p),'Find UI elements')
    assert o.provider=='fake-vision' and o.elements[0].label=='Planner'
    assert o.evidence.content_hash

def test_image_analysis_never_sends_image_to_generic_text_router(tmp_path):
    p=tmp_path/'screen.png'; p.write_bytes(b'image')
    class TextOnlyRouter:
        def ask(self,*args,**kwargs): raise AssertionError('text-only route must not receive image')
    a=MultimodalAnalyzer(router=TextOnlyRouter())
    import pytest
    with pytest.raises(RuntimeError, match='no explicit vision route'):
        a.analyze_image(str(p))

def test_pdf_document_understanding(tmp_path):
    p=tmp_path/'note.txt'; p.write_text('Alice should learn from this document.')
    a=MultimodalAnalyzer(router=FakeRouter())
    o=a.analyze_document(str(p))
    assert 'Alice should learn' in o.extracted_text
    assert o.summary=='A short document'

def test_svg_routes_to_visual_understanding(tmp_path):
    p=tmp_path/'diagram.svg'; p.write_text('<svg></svg>')
    a=MultimodalAnalyzer(vision_router=FakeVision())
    assert a.analyze(str(p)).evidence.kind==MediaKind.SVG

def test_screen_and_camera_entrypoints_are_explicit(tmp_path, monkeypatch):
    p=tmp_path/'frame.png'; p.write_bytes(b'frame')
    a=MultimodalAnalyzer(vision_router=FakeVision())
    o=a.analyze_camera_frame(str(p))
    assert o.evidence.kind==MediaKind.IMAGE
    import sys, types
    fake=types.ModuleType('alice.vision.screen')
    fake.screenshot=lambda path=None: {'path':str(p)}
    monkeypatch.setitem(sys.modules, 'alice.vision.screen', fake)
    o=a.analyze_screen()
    assert o.evidence.kind==MediaKind.IMAGE
