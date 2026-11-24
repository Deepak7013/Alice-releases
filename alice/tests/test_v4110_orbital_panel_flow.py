from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "alice/ui/assets/alice-premium-ui.html").read_text(encoding="utf-8")
CSS = (ROOT / "alice/ui/assets/alice-native-orbital-ui.css").read_text(encoding="utf-8")

class OrbitalPanelFlowTests(unittest.TestCase):
    def test_orbital_node_origin_is_captured(self):
        self.assertIn("--orbit-origin-x", HTML)
        self.assertIn("--orbit-origin-y", HTML)
        self.assertIn("nodeRect=node.getBoundingClientRect()", HTML)

    def test_panel_opening_uses_dynamic_origin(self):
        self.assertIn("transform-origin:var(--orbit-origin-x,18%) var(--orbit-origin-y,45%)", CSS)

    def test_selected_particle_has_handoff_animation(self):
        self.assertIn("node.classList.add('is-selected')", HTML)
        self.assertIn(".orbital-node.is-selected::after", CSS)
        self.assertIn("@keyframes orbitParticleHandoff", CSS)

    def test_reduced_motion_is_respected(self):
        self.assertIn("@media (prefers-reduced-motion: reduce)", CSS)
        self.assertIn("animation-duration: .01ms !important", CSS)

if __name__ == "__main__":
    unittest.main()
