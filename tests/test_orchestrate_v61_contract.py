from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"


class OrchestrateV61ContractTests(unittest.TestCase):
    def test_release_manifest_tracks_the_subtractive_upgrade(self) -> None:
        manifest = json.loads(
            (SKILL / "manifests" / "61.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["skill_version"], 61)
        self.assertEqual(manifest["orchestrate_compat"], 61)
        self.assertEqual(manifest["release_delta"]["from_version"], 60)
        self.assertIn("SKILL.md", manifest["release_delta"]["must_reread"])
        self.assertIn(
            "references/dispatch-packets.md",
            manifest["release_delta"]["must_reread"],
        )
        self.assertIn(
            "references/wave-pipeline.md",
            manifest["release_delta"]["must_reread"],
        )
        self.assertIn(
            "references/critical-review.md",
            manifest["release_delta"]["must_reread"],
        )

    def test_every_runtime_and_role_profile_is_compat_61(self) -> None:
        for path in (
            *sorted((SKILL / "references").glob("*.md")),
            SKILL / "runtime-codex.md",
            SKILL / "runtime-claude.md",
            ROOT / "home" / ".codex" / "agents" / "contract-planner.toml",
            ROOT / "home" / ".codex" / "agents" / "implementer.toml",
            ROOT / "home" / ".codex" / "agents" / "reviewer.toml",
            ROOT / "home" / ".claude" / "agents" / "contract-planner.md",
            ROOT / "home" / ".claude" / "agents" / "implementer.md",
            ROOT / "home" / ".claude" / "agents" / "reviewer.md",
        ):
            self.assertIn(
                "orchestrate_compat: 61", path.read_text(encoding="utf-8"), path
            )

    def test_role_profiles_are_standing_orders_not_process_manuals(self) -> None:
        for directory, suffix in (
            (ROOT / "home" / ".codex" / "agents", ".toml"),
            (ROOT / "home" / ".claude" / "agents", ".md"),
        ):
            for role in ("contract-planner", "implementer", "reviewer"):
                path = directory / f"{role}{suffix}"
                self.assertLessEqual(len(path.read_bytes()), 5_000, path)


if __name__ == "__main__":
    unittest.main()
