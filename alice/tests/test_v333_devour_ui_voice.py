from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def ui(): return (ROOT/"alice/ui/app.py").read_text(encoding="utf-8")
def test_version(): assert (ROOT/"VERSION.txt").read_text().strip().startswith("ALICE v")
def test_modes_use_real_menu_entries():
    t=ui(); assert "self.tools_menu.entryconfigure(self.text_menu_index" in t; assert "self.tools_menu.entryconfigure(self.concise_menu_index" in t; assert "self.text_button.config" not in t and "self.concise_button.config" not in t
def test_bubble_drag_and_tools():
    t=ui(); assert "self._bubble_drag=" in t; assert "self._bubble_drag_move" in t; assert "self._bubble_menu.tk_popup" in t; assert "Voice & Microphone" in t; assert "self._bubble_state_path" in t
def test_snap_safe_window_hide():
    t=ui(); assert "self.root.iconify()" in t; assert "self.root.withdraw()" not in t; assert "snap/split placement" in t
def test_window_persistence():
    t=ui(); assert "self._window_state_path" in t; assert "self._window_fullscreen" in t; assert 'self.root.attributes("-fullscreen",self._window_fullscreen)' in t
def test_voice_test_worker():
    t=ui(); assert 'name="AliceVoiceTest"' in t; assert 'self._queue_ui("voice_test"' in t; assert "Voice test failed" in t
def test_neural_playback_path():
    t=(ROOT/"alice/voice/neural.py").read_text(); assert "ALICE_TTS_PATH" in t; assert "Neural audio file was not found." in t; assert "Timed out waiting for neural audio metadata." in t
def test_neural_selection_and_strict_mode():
    t=(ROOT/"alice/voice/voice.py").read_text(); assert "self.stop()" in t[t.index("def select_female_neural"):t.index("def current_mode")]; b=t[t.index("def _speak_with_recovery"):t.index("def female_voice_packs")]; assert '=="neural"' in b; assert "return False" in b
def test_devour_v2():
    t=(ROOT/"alice/gluttony/evolver.py").read_text(); assert "alice_capability_assessment" in t; assert "def latest_report" in t
def test_assessor_is_conservative():
    from alice.gluttony.assessment import assess_capabilities
    r=assess_capabilities(ROOT,[{"name":"model_provider_abstraction","evidence_score":4}]); assert r["capabilities"][0]["status"] in {"exists","partial"}; assert r["automatic_absorption"]==[]

def test_background_finish_does_not_resurrect_hidden_window():
    t=ui(); block=t[t.index("def _refocus_entry"):t.index("def _restore_window_state")]; assert "root.deiconify" not in block; assert 'state()=="iconic"' in block
