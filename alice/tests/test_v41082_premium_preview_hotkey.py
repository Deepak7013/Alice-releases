from pathlib import Path


def test_window_close_keeps_alice_resident_and_explicit_shutdown_remains_available():
    root = Path(__file__).resolve().parents[2]
    source = (root / "alice" / "ui" / "app.py").read_text(encoding="utf-8")
    assert 'self.root.protocol("WM_DELETE_WINDOW", self.hide_window)' in source
    assert 'menu.add_command(label="Shutdown ALICE",command=self.shutdown)' in source


def test_premium_ui_preview_is_bundled_and_labeled_as_preview():
    root = Path(__file__).resolve().parents[2]
    preview = root / "alice" / "ui" / "assets" / "alice-premium-ui-preview.html"
    assert preview.is_file()
    html = preview.read_text(encoding="utf-8")
    assert "PREVIEW MODE" in html
    assert "connect this UI to your existing ALICE runtime API" in html
    source = (root / "alice" / "ui" / "app.py").read_text(encoding="utf-8")
    assert 'menu.add_command(label="Premium UI Preview",command=self.open_premium_ui_preview)' in source
    assert 'webbrowser.open(preview.as_uri())' in source


def test_v41082_installer_offers_current_user_install_for_protected_data_migration():
    root = Path(__file__).resolve().parents[2]
    installer = (root / "INSTALL_ALICE.ps1").read_text(encoding="utf-8")
    assert '"C:\\Alice_v4.108.1"' in installer
    assert '"C:\\Alice_v4.108.0"' in installer
    assert "Copy-Protected $old $Stage" in installer


def test_premium_html_is_the_default_live_window_and_chat_uses_runtime_bridge():
    root = Path(__file__).resolve().parents[2]
    source = (root / "alice" / "ui" / "app.py").read_text(encoding="utf-8")
    html = (root / "alice" / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")
    assert 'assets" / "alice-premium-ui.html' in source
    assert 'webview.create_window(' in source and 'js_api=bridge' in source and 'bridge.bind(app)' in source
    assert 'window.pywebview.api.send_message(submitted)' in html
    assert 'api.poll_events(eventCursor)' in html
    assert 'I’ve received your message in the interface preview' not in html


def test_old_terminal_rollback_journal_does_not_repeat_startup_notice():
    root = Path(__file__).resolve().parents[2]
    source = (root / "alice" / "ui" / "app.py").read_text(encoding="utf-8")
    assert 'self._update_recovery.get("state")=="ROLLED_BACK" and self._update_recovery.get("recovered") is True' in source
