from pathlib import Path


def _text():
    return (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")


def test_all_worker_or_callback_tk_handoffs_use_ui_queue():
    text = _text()
    assert 'GlobalHotkey(lambda:self._queue_ui("mini_hotkey"))' in text
    assert 'self._queue_ui("heard", text)' in text
    assert 'self._queue_ui("shutdown")' in text
    assert 'self.root.after(0,done)' not in text
    assert 'self.root.after(0,self.toggle_window)' not in text
    assert 'self.root.after(200, self.shutdown)' not in text


def test_single_instance_guards_and_compatibility_entrypoint():
    root = Path(__file__).resolve().parents[2]
    main = (root / "alice" / "__main__.py").read_text(encoding="utf-8")
    app = (root / "alice" / "app.py").read_text(encoding="utf-8")
    assert 'CreateMutexW' in main
    assert 'CreateFileW' in main
    assert 'alice-ui.lock' in main
    assert 'if not _acquire_single_instance() or not _acquire_exclusive_lock():' in main
    assert 'from .__main__ import main' in app


def test_release_version_and_install_target():
    root = Path(__file__).resolve().parents[2]
    assert (root / "VERSION.txt").read_text(encoding="utf-8").strip() .startswith("ALICE v")
    ps = (root / "INSTALL_ALICE.ps1").read_text(encoding="utf-8")
    bat = (root / "INSTALL_ALICE.bat").read_text(encoding="utf-8")
    assert "ALICE_INSTALL_ROOT" in ps
    assert 'set "TARGET=C:\\Alice_v%VERSION%"' in bat
