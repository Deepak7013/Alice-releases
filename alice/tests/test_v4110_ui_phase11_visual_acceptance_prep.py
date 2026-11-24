from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = (ROOT / "tools/capture_alice_ui_acceptance.ps1").read_text(encoding="utf-8")
RUNBOOK = (ROOT / "ALICE_UI_PHASE11_LIVE_VISUAL_ACCEPTANCE_RUNBOOK.md").read_text(encoding="utf-8")

def test_capture_script_is_non_invasive_and_saves_png_with_hash():
    assert "CopyFromScreen" in CAPTURE
    assert "ImageFormat]::Png" in CAPTURE
    assert "Get-FileHash -Algorithm SHA256" in CAPTURE
    assert "Start-Process" not in CAPTURE
    assert "Remove-Item" not in CAPTURE
    assert "Set-Content" not in CAPTURE

def test_capture_script_disposes_graphics_resources():
    assert "finally {" in CAPTURE
    assert "$graphics.Dispose()" in CAPTURE
    assert "$bitmap.Dispose()" in CAPTURE

def test_runbook_requires_review_environment_and_sensitive_content_check():
    assert "isolated review environment" in RUNBOOK
    assert "credentials" in RUNBOOK
    assert "does not launch, install, modify, or control ALICE" in RUNBOOK

def test_runbook_covers_all_required_views_and_open_acceptance_gates():
    for token in ("01-workspace-full.png", "02-immersive-full.png",
                  "03-orbital-launcher.png", "04-feature-panel.png",
                  "05-voice-console.png", "Live Windows WebView rendering: NOT RUN"):
        assert token in RUNBOOK
