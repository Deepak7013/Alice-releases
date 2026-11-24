import hashlib
import json
import struct
import zipfile
from pathlib import Path
import pytest

from alice.gluttony.assimilation import AssimilationEngine
from alice.gluttony.evolver import DevourEngine
from alice.gluttony.intake import LocalInputAdapter
from alice.gluttony.review import DevourReviewStore
from alice.gluttony.review import DevourReviewError


def _utf8(value):
    raw=value.encode("utf-8")
    return b"\x01"+struct.pack(">H",len(raw))+raw


def _minimal_java_class():
    constants=(
        _utf8("JarCapability")+b"\x07\x00\x01"+
        _utf8("java/lang/Object")+b"\x07\x00\x03"+
        _utf8("run")+_utf8("()V")+_utf8("enabled")+_utf8("Z")
    )
    body=(b"\xca\xfe\xba\xbe"+struct.pack(">HHH",0,52,9)+constants+
          struct.pack(">HHHHH",0x0021,2,4,0,1)+
          struct.pack(">HHHH",0x0001,7,8,0)+
          struct.pack(">H",1)+struct.pack(">HHHH",0x0001,5,6,0)+
          struct.pack(">H",0))
    return body


def test_directory_intake_keeps_unknown_files_for_hash_based_review(tmp_path):
    source=tmp_path/"candidate"
    source.mkdir()
    raw=b"\x00\xffopaque application payload"
    (source/"bundle.weird").write_bytes(raw)
    (source/"README.md").write_text("A small project",encoding="utf-8")
    (source/".env").write_text("TOKEN=not-for-copy",encoding="utf-8")
    work=tmp_path/"job"
    work.mkdir()

    result=LocalInputAdapter().stage(source,work)
    engine=AssimilationEngine(tmp_path)
    inventory=engine._inventory(result.source)
    row=next(item for item in inventory["files"] if item["path"]=="bundle.weird")

    assert result.files_copied==2
    assert (result.source/"bundle.weird").read_bytes()==raw
    assert not (result.source/".env").exists()
    assert row["parser"]=="metadata_only_binary"
    assert row["sha256"]==hashlib.sha256(raw).hexdigest()


def test_jar_is_recognized_and_static_class_signatures_are_reviewable(tmp_path):
    jar=tmp_path/"sample.jar"
    class_bytes=_minimal_java_class()
    with zipfile.ZipFile(jar,"w") as archive:
        archive.writestr("com/example/JarCapability.class",class_bytes)
        archive.writestr("META-INF/MANIFEST.MF","Manifest-Version: 1.0\n")
    engine=DevourEngine(tmp_path,gluttony=AssimilationEngine(tmp_path),self_manager=object())

    result=engine.devour(jar)
    report=json.loads((tmp_path/"alice_workspace"/"gluttony"/"devour"/Path(result["report"]).name).read_text(encoding="utf-8"))
    module=next(row for row in report["architecture"]["modules"] if row["language"]=="java_bytecode_static")
    review=DevourReviewStore(tmp_path).inspect(result["report"])

    assert report["acquisition"]["input_format"]=="jar"
    assert report["acquisition"]["input_sha256"]==hashlib.sha256(jar.read_bytes()).hexdigest()
    assert module["class_name"]=="JarCapability"
    assert module["fields"][0]["name"]=="enabled"
    assert module["methods"][0]["name"]=="run"
    assert any(row["path"].endswith("JarCapability.class") for row in review["architecture"]["file_catalog"])
    assert review["architecture"]["file_analysis_coverage"]["external_code_executed"] is False
    assert engine.verify_single_postcondition({"source":str(jar)},result).ok is True


def test_source_inventory_lists_supported_static_function_names(tmp_path):
    source=tmp_path/"project"
    source.mkdir()
    (source/"agent.py").write_text("class Agent:\n    def run(self):\n        pass\n",encoding="utf-8")
    (source/"client.js").write_text("export function connect() {}\nconst retry = () => true;\n",encoding="utf-8")
    engine=AssimilationEngine(tmp_path)
    inventory=engine._inventory(source)
    analysis=engine._analyze(source,inventory)
    names={module["path"]:[symbol["name"] for symbol in module.get("symbol_names",[])]
           for module in analysis["modules"]}

    assert names["agent.py"]==["Agent","run"]
    assert names["client.js"]==["connect","retry"]
    assert analysis["file_analysis_coverage"]["total_files"]==2


def test_ui_adaptation_request_requires_separate_capability_approval(tmp_path):
    source=tmp_path/"project"
    source.mkdir()
    (source/"ui.html").write_text("frontend user interface dashboard theme layout component stylesheet view",encoding="utf-8")
    report=DevourEngine(tmp_path,gluttony=AssimilationEngine(tmp_path),self_manager=object()).devour(source)
    capability="user_interface"
    assert any(row["name"]==capability for row in report["capabilities"])
    reviews=DevourReviewStore(tmp_path)

    with pytest.raises(DevourReviewError,match="1000 characters"):
        reviews.approve_capability(report["report"],capability,confirmed=True,
                                   ui_request="x"*1001)
    reviews.approve_capability(report["report"],capability,confirmed=True,
                               decision="implement_native_equivalent",
                               ui_request="Use ALICE's cyan HUD with an optional compact chat panel.")
    evidence=reviews.approval_evidence(report["report"],[capability])

    assert evidence["ui_requests"][capability]=="Use ALICE's cyan HUD with an optional compact chat panel."
    assert reviews.inspect(report["report"])["capabilities"][0]["ui_request"]==evidence["ui_requests"][capability]


def test_devour_review_prompts_before_ui_adaptation_and_exposes_inventory():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text(encoding="utf-8")

    assert 'messagebox.askyesno("Adapt ALICE\'s UI?"' in source
    assert 'simpledialog.askstring("Describe your UI adaptation"' in source
    assert 'command=self._show_devour_inventory' in source
    assert "Source Inventory / Functions" in source
