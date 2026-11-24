from pathlib import Path


def test_gluttony_services_are_initialized_before_tool_registry_build():
    text = Path("alice/ui/app.py").read_text(encoding="utf-8")
    gluttony_pos = text.index("self.gluttony=AssimilationEngine(self.root_path)")
    devour_pos = text.index("self.devour=DevourEngine(self.root_path,self.gluttony,capability_manager=self.capabilities)")
    tools_pos = text.index("self.tools=self.build_tools()")
    assert gluttony_pos < tools_pos
    assert devour_pos < tools_pos


def test_ui_version_and_devour_wiring_are_current():
    text = Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert 'self.root.title(f"Alice — {self._generation_name()} {self._app_version()}")' in text
    assert 'from ..gluttony import AssimilationEngine, DevourEngine' in text
    assert 't.add("devour_repository"' in text
