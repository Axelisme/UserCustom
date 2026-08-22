"""Every shipped top-level pi extension has to load through pi itself."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = ROOT / "home/.pi/agent/extensions"
HARNESS = ROOT / "tests/collab_op_extension_harness.mjs"
PI_PACKAGE = Path("/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js")


class PiExtensionLoadTests(unittest.TestCase):
    def test_every_shipped_extension_loads(self) -> None:
        shipped = sorted(EXTENSIONS.glob("*.ts"))
        self.assertTrue(shipped, f"no extensions found under {EXTENSIONS}")
        for extension in shipped:
            with self.subTest(extension=extension.name):
                loaded = subprocess.run(
                    ["node", str(HARNESS), str(PI_PACKAGE), str(extension), str(ROOT)],
                    input='{"tool":"missing"}\n',
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(loaded.returncode, 0, loaded.stdout + loaded.stderr)


if __name__ == "__main__":
    unittest.main()
