from __future__ import annotations

import hashlib
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home/.codex/skills/planning-with-files"
SCRIPT = SKILL / "scripts/plan.py"
PI_SCRIPT = ROOT / "home/.pi/agent/skills/planning-with-files/scripts/plan.py"


class RetiredPlanningCapsuleTests(unittest.TestCase):
    def test_capsule_identity_refuses_new_task_authority(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "Retired transition capsule",
            "must not create or manage new tasks",
            "direct legacy diagnostics only",
            "dev-flow",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_direct_legacy_diagnostics_entrypoint_remains_executable(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("status", result.stdout)
        self.assertIn("check", result.stdout)
        self.assertEqual(PI_SCRIPT.resolve(), SCRIPT.resolve())

    def test_capsule_script_and_templates_retain_their_v135_bytes(self) -> None:
        expected = {
            "scripts/plan.py": "c1100136c16bbaaf710db8e6df960b03915b1dac1cf6e59a65aa169e623c06c3",
            "templates/INDEX.md": "16b8ba26b2cbf537c986e2ef6168f23d242723db36117c8c55141bceaffc542a",
            "templates/findings.md": "ced98cfbcddd4cec645c00a448a45630116832d46d4cf9a9e8af6b163a300f47",
            "templates/phase.md": "2f425f8317b2c952afdbc861c6cd7098bcf88da0310e88f487287ff344268953",
        }
        for relative, digest in expected.items():
            with self.subTest(relative=relative):
                observed = hashlib.sha256((SKILL / relative).read_bytes()).hexdigest()
                self.assertEqual(observed, digest)


if __name__ == "__main__":
    unittest.main()
