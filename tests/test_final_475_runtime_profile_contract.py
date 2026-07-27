from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
RUNTIME_BINDINGS = {
    "codex-in-codex-tree": HOME / ".codex/skills/orchestrate/runtime-codex.md",
    "codex-in-pi-tree": HOME / ".pi/agent/skills/orchestrate/runtime-codex.md",
    "pi-in-codex-tree": HOME / ".codex/skills/orchestrate/runtime-pi.md",
    "pi-in-pi-tree": HOME / ".pi/agent/skills/orchestrate/runtime-pi.md",
}
ROLE_PROFILES = {
    "oracle-codex": HOME / ".codex/agents/wave-oracle.toml",
    "oracle-claude": HOME / ".claude/agents/wave-oracle.md",
    "oracle-pi": HOME / ".pi/agent/agents/wave-oracle.md",
    "implementer-codex": HOME / ".codex/agents/wave-implementer.toml",
    "implementer-claude": HOME / ".claude/agents/wave-implementer.md",
    "implementer-pi": HOME / ".pi/agent/agents/wave-implementer.md",
}


def normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class Final475RuntimeIdentityContractTests(unittest.TestCase):
    """Source Contract for stable native task identity in Codex and Pi."""

    def test_runtime_bindings_freeze_item_identity_and_git_recovery(self) -> None:
        for binding, path in RUNTIME_BINDINGS.items():
            with self.subTest(binding=binding):
                text = normalized(path)
                self.assertIn("role stream identity is exactly `<task-id>.<wave-id>.<role>`", text)
                self.assertIn("stable runtime item identity is `slice-<slice-id>`", text)
                self.assertIn("no attempt detail", text)
                self.assertIn("ready SHA", text)
                self.assertIn("runtime task", text)
                self.assertIn("completed", text)
                self.assertIn("native", text.lower())
                self.assertTrue("Git/task plan" in text or "Git/task-plan" in text or "task plan" in text)
                self.assertIn("recover position", text)


class Final475TerminalTestEvidenceContractTests(unittest.TestCase):
    """Source Contract for test evidence in every Oracle/Implementer mirror."""

    def test_terminal_output_carries_role_specific_focused_test_evidence(self) -> None:
        for profile, path in ROLE_PROFILES.items():
            with self.subTest(profile=profile):
                text = normalized(path)
                self.assertIn("terminal task output", text.lower())
                self.assertIn("exact focused test command(s)", text)
                self.assertIn("Slice", text)
                self.assertIn("exact SHA", text)
                if profile.startswith("oracle-"):
                    self.assertIn("observed red result(s)", text)
                    self.assertIn("distinguish intended missing behavior", text)
                    for term in ("import", "syntax", "fixture"):
                        self.assertIn(term, text.lower())
                else:
                    self.assertIn("observed green result(s)", text)
                    self.assertIn("Contract suite green", text)


if __name__ == "__main__":
    unittest.main()
