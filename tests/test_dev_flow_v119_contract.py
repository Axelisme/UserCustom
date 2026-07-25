from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
DEV_FLOW_PATHS = (
    HOME / ".codex" / "skills" / "dev-flow" / "SKILL.md",
    HOME / ".pi" / "agent" / "skills" / "dev-flow" / "SKILL.md",
    HOME / ".claude" / "skills" / "dev-flow" / "SKILL.md",
)


class DevFlowV119ContractTests(unittest.TestCase):
    """Oracle-owned package contract for the v119 acceptance handoff.

    This intentionally checks the installed documentation seam rather than a
    private implementation.  The three runtime overlays are one shared skill
    contract and must not quietly describe different acceptance workflows.
    """

    def docs(self) -> tuple[str, ...]:
        return tuple(path.read_text(encoding="utf-8") for path in DEV_FLOW_PATHS)

    def test_runtime_overlays_are_one_v119_acceptance_contract(self) -> None:
        documents = self.docs()
        normalized = {" ".join(document.split()) for document in documents}
        self.assertEqual(len(normalized), 1)
        document = next(iter(normalized))

        # The reviewed candidate is the post-simplify SHA.  Use the complete
        # labels so an old "code-review + simplify" summary cannot satisfy this.
        sequence = (
            "simplify",
            "canonical tests",
            "clean-detached",
            "code-review",
        )
        for label in sequence:
            self.assertIn(label, document)
        positions = [document.index(label) for label in sequence]
        self.assertEqual(positions, sorted(positions), document)
        self.assertIn("exact SHA", document)
        self.assertIn("post-simplify", document)

        # A material contract finding goes back through both role streams in
        # this Wave; quality-only cleanup never reopens Oracle.
        self.assertRegex(document, r"needs_fix")
        self.assertRegex(document, r"needs_fix.{0,240}new Wave")
        self.assertRegex(document, r"Spec.{0,240}Oracle.{0,240}Implementation")
        self.assertRegex(document, r"quality.{0,240}Implementation")
        self.assertRegex(
            document,
            r"(?:After a fix|correction).{0,260}regenerate.{0,120}Git profile"
            r".{0,260}simplify.{0,160}canonical tests.{0,200}clean-detached"
            r".{0,80}code-review",
        )

        # Handoff is deliberately a small exact-SHA tuple, not a second ledger.
        for term in (
            "exact base SHA",
            "Implementation SHA",
            "frozen spec",
            "task plan",
            "canonical test results",
            "Git profile JSON",
            "without a receipt",
            "without a finding",
        ):
            self.assertIn(term, document)

        self.assertRegex(document, r"contract tests.{0,160}immutable")
        self.assertRegex(document, r"identit(?:y|ies).{0,160}worktree")
        self.assertRegex(document, r"landing.{0,240}outside orchestrate")
        self.assertRegex(document, r"current user authority")

if __name__ == "__main__":
    unittest.main()
