from __future__ import annotations

import stat
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TDD = ROOT / "home" / ".codex" / "skills" / "tdd"


class TddGateExecutableTests(unittest.TestCase):
    def test_gate_asset_is_an_executable_incomplete_template(self) -> None:
        asset = TDD / "assets" / "gate.sh"
        self.assertTrue(asset.is_file())
        self.assertTrue(asset.stat().st_mode & stat.S_IXUSR)

        syntax = subprocess.run(
            ["bash", "-n", str(asset)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

        unadapted = subprocess.run(
            [str(asset), "green"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(unadapted.returncode, 2)
        self.assertIn("incomplete template", unadapted.stderr)


if __name__ == "__main__":
    unittest.main()
