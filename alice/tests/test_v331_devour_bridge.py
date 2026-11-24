from pathlib import Path
import json, zipfile
import pytest
from alice.gluttony.assimilation import AssimilationEngine
from alice.gluttony.evolver import DevourEngine, DevourError


def test_devour_engine_supports_zip_folder_and_url_paths():
    text=Path("alice/gluttony/evolver.py").read_text(encoding="utf-8")
    intake=Path("alice/gluttony/intake.py").read_text(encoding="utf-8")
    assert "local_zip" in intake
    assert "local_directory" in intake
    assert "LocalInputAdapter" in text
    assert "_acquire" in text
    assert "never_execute_external_code" in text


def test_devour_bridge_requires_explicit_upgrade_approval(tmp_path):
    text=Path("alice/gluttony/evolver.py").read_text(encoding="utf-8")
    app=Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert "approve capabilities individually" in text
    assert 'auto_upgrade=True, approval_token="USER_APPROVED_DEVOUR_UPGRADE"' not in app
    engine=DevourEngine(tmp_path,AssimilationEngine(tmp_path))
    with pytest.raises(DevourError,match="approve capabilities individually"):
        engine.devour("unused",auto_upgrade=True,approval_token="USER_APPROVED_DEVOUR_UPGRADE")


def test_devour_native_reimplementation_is_governed():
    text=Path("alice/maintenance/self_manager.py").read_text(encoding="utf-8")
    assert "def prepare_devour_upgrade" in text
    assert "External code must never execute" in text
    assert "_package_candidate" in text
    assert "_stage_test" in text


def test_devour_ui_tool_is_exposed():
    text=Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert "DevourEngine" in text
    assert 't.add("devour_repository"' in text
    assert 't.add("devour_discover"' in text
    assert "self.devour.devour" in text


def test_devour_report_schema_has_native_reimplementation_plan():
    text=Path("alice/gluttony/evolver.py").read_text(encoding="utf-8")
    assert '"reimplementation_plan"' in text
    assert '"source_samples"' in text
