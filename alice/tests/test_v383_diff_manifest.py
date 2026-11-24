from alice.engineering.diff_manifest import make_manifest
def test_diff_manifest_is_deterministic():
 a=make_manifest({'files':['b.py','a.py'],'changed_lines':4}); b=make_manifest({'files':['a.py','b.py'],'changed_lines':4}); assert a.digest==b.digest and a.files==['a.py','b.py']
