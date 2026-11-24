from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "alice/ui/assets/alice-native-orbital-ui.css").read_text(encoding="utf-8")

class ResponsiveCrystalPanelTests(unittest.TestCase):
    def test_phase_four_styles_are_present(self):
        self.assertIn("Phase 4 — responsive crystal-panel choreography", CSS)
        self.assertIn("--alice-crystal-surface", CSS)
        self.assertIn("--alice-crystal-shadow", CSS)

    def test_small_screen_panels_are_scrollable_and_stack(self):
        self.assertIn("@media (max-width: 600px)", CSS)
        self.assertIn("max-height: calc(100dvh - 118px)", CSS)
        self.assertIn("grid-template-columns: minmax(0, 1fr) !important", CSS)

    def test_keyboard_focus_is_visible(self):
        self.assertIn(":focus-visible", CSS)
        self.assertIn("outline: 2px solid rgba(111, 245, 218, .92)", CSS)

    def test_reduced_motion_preference_is_not_overridden(self):
        self.assertIn("@media (prefers-reduced-motion: no-preference)", CSS)

if __name__ == "__main__":
    unittest.main()
