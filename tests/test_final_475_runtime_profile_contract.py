from __future__ import annotations

import unittest
from pathlib import Path


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

    def test_runtime_bindings_freeze_stream_item_completion_and_recovery(self) -> None:
        for binding, path in RUNTIME_BINDINGS.items():
            with self.subTest(binding=binding):
                text = normalized(path)
                self.assertRegex(
                    text,
                    r"(?i)role stream identity is exactly\s*`<task-id>\.<wave-id>\.<role>`",
                    "the role stream must have one exact cross-runtime identity",
                )
                self.assertRegex(
                    text,
                    r"(?i)stable runtime item identity is\s*`slice-<slice-id>`"
                    r".{0,100}(?:no|without|does not contain).{0,40}attempt detail",
                    "runtime items must remain stable across Contract attempts",
                )
                self.assertRegex(
                    text,
                    r"(?i)Root.{0,80}consumes?.{0,80}ready SHA.{0,100}only after"
                    r".{0,100}corresponding runtime task.{0,50}(?:has )?completed",
                    "a ready SHA is not consumable while its runtime task is still active",
                )
                self.assertRegex(
                    text,
                    r"(?i)(?:restart|continuation).{0,160}native"
                    r".{0,240}(?:Git.{0,80}(?:task )?plan|(?:task )?plan.{0,80}Git)"
                    r".{0,100}recover.{0,60}position",
                    "native continuation must coexist with Git/plan recovery authority",
                )


class Final475TerminalTestEvidenceContractTests(unittest.TestCase):
    """Source Contract for test evidence in every Oracle/Implementer mirror."""

    def test_terminal_output_carries_role_specific_focused_test_evidence(self) -> None:
        for profile, path in ROLE_PROFILES.items():
            with self.subTest(profile=profile):
                text = normalized(path)
                self.assertRegex(
                    text,
                    r"(?i)terminal task output.{0,240}exact focused test command\(s\)"
                    r".{0,240}observed (?:red|green) result\(s\)",
                    "terminal output must reproduce commands and observed results",
                )
                self.assertRegex(
                    text,
                    r"(?i)(?:alongside.{0,120}Slice.{0,120}(?:exact|full exact) SHA"
                    r"|Slice.{0,120}(?:exact|full exact) SHA.{0,120}alongside)",
                    "focused evidence belongs alongside Slice and exact SHA",
                )
                if profile.startswith("oracle-"):
                    self.assertRegex(
                        text,
                        r"(?i)observed red result\(s\).{0,240}distinguish"
                        r".{0,160}intended missing behavior.{0,160}import"
                        r".{0,80}syntax.{0,80}fixture",
                        "Oracle red evidence must identify behavior, not harness defects",
                    )
                else:
                    self.assertRegex(
                        text,
                        r"(?i)observed green result\(s\).{0,200}Contract suite.{0,60}green",
                        "Implementer evidence must show the frozen Contract suite green",
                    )


if __name__ == "__main__":
    unittest.main()
