from __future__ import annotations

import importlib
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
CODEX_SKILL = HOME / ".codex" / "skills" / "orchestrate"
PI_SKILL = HOME / ".pi" / "agent" / "skills" / "orchestrate"
VERSION_MATCH = re.search(
    r"(?m)^skill_version: (\d+)$",
    (CODEX_SKILL / "SKILL.md").read_text(encoding="utf-8"),
)
if VERSION_MATCH is None:
    raise RuntimeError("orchestrate SKILL.md has no skill_version")
SHIPPED_VERSION = int(VERSION_MATCH.group(1))


def load_release_module():
    sys.path.insert(0, str(CODEX_SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.release")
    finally:
        sys.path.pop(0)


class PiRuntimeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.release = load_release_module()

    def test_source_home_resolves_all_runtime_layouts(self) -> None:
        self.assertEqual(self.release.source_home(CODEX_SKILL), HOME.resolve())
        self.assertEqual(self.release.source_home(PI_SKILL), HOME.resolve())
        with self.assertRaisesRegex(Exception, "cannot locate home root"):
            self.release.source_home(Path("/tmp/unsupported/skills/orchestrate"))

    def test_manifest_inventory_covers_every_runtime_and_profile(self) -> None:
        for skill in (CODEX_SKILL, PI_SKILL):
            manifest = self.release.build_manifest(skill, SHIPPED_VERSION)
            self.assertTrue(
                {"runtime-codex.md", "runtime-claude.md", "runtime-pi.md"}
                <= set(manifest["documents"])
            )
            expected = {
                path.relative_to(HOME).as_posix()
                for path in self.release.profile_paths(HOME)
                if path.is_file()
            }
            self.assertEqual(set(manifest["profiles"]), expected)
            self.assertIn(".codex/agents/wave-oracle.toml", manifest["profiles"])
            self.assertNotIn(".codex/agents/wave-reviewer.toml", manifest["profiles"])

    def test_profile_contracts_match_across_runtimes(self) -> None:
        for name in (
            "acceptance-reviewer",
            "contract-planner",
            "wave-oracle",
            "wave-implementer",
        ):
            files = (
                (HOME / ".codex" / "agents" / f"{name}.toml", ".toml"),
                (HOME / ".claude" / "agents" / f"{name}.md", ".md"),
                (HOME / ".pi" / "agent" / "agents" / f"{name}.md", ".md"),
            )
            bodies = {
                self.release.normalized_sha256(
                    self.release.profile_standing_orders(path.read_text(encoding="utf-8"), suffix)
                )
                for path, suffix in files
            }
            self.assertEqual(len(bodies), 1, name)

    def test_pi_runtime_owns_pipelinemanager_and_pipeline_capability(self) -> None:
        text = " ".join((CODEX_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split())
        self.assertIn("PipelineManager", text)
        self.assertIn("pipeline capability", text.lower())

    def test_codex_and_claude_profiles_do_not_advertise_pipeline_capability(self) -> None:
        for runtime, root, suffix in (
            ("codex", HOME / ".codex" / "agents", ".toml"),
            ("claude", HOME / ".claude" / "agents", ".md"),
        ):
            for role in ("wave-oracle", "wave-implementer"):
                with self.subTest(runtime=runtime, role=role):
                    text = (root / f"{role}{suffix}").read_text(encoding="utf-8")
                    self.assertNotRegex(text, r"(?m)^pipeline:\s*true\s*$")
        for role in ("wave-oracle", "wave-implementer"):
            pi = (HOME / ".pi" / "agent" / "agents" / f"{role}.md").read_text(
                encoding="utf-8"
            )
            self.assertRegex(pi, r"(?m)^pipeline:\s*true\s*$")

    def test_acceptance_profiles_expose_full_and_bounded_review_modes(self) -> None:
        for runtime, root, suffix in (
            ("codex", HOME / ".codex" / "agents", ".toml"),
            ("claude", HOME / ".claude" / "agents", ".md"),
            ("pi", HOME / ".pi" / "agent" / "agents", ".md"),
        ):
            path = root / f"acceptance-reviewer{suffix}"
            text = " ".join(path.read_text(encoding="utf-8").split())
            with self.subTest(runtime=runtime):
                self.assertIn("Review scope: full_milestone | bounded_delta", text)
                self.assertIn("Checkout mode: integration | detached_fallback", text)
                self.assertIn("exact SHA", text)

    def test_pi_profiles_keep_runtime_frontmatter_contract(self) -> None:
        for name in ("wave-oracle", "wave-implementer"):
            text = (HOME / ".pi" / "agent" / "agents" / f"{name}.md").read_text(
                encoding="utf-8"
            )
            for key in (
                "model:",
                "thinking:",
                "tools:",
                "systemPromptMode:",
                "inheritProjectContext:",
                "inheritSkills:",
                "pipeline:",
            ):
                self.assertIn(key, text)

    def test_doctor_detects_shipped_profile_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "home" / ".codex" / "skills" / "orchestrate"
            skill.parent.mkdir(parents=True)
            shutil.copytree(CODEX_SKILL, skill)
            profile = root / "home" / ".codex" / "agents" / "wave-oracle.toml"
            profile.parent.mkdir(parents=True)
            shutil.copy2(HOME / ".codex" / "agents" / "wave-oracle.toml", profile)
            profile.write_text(profile.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")
            result = self.release.verify_release(skill)
            self.assertFalse(result["ok"])
            self.assertTrue(any("wave-oracle" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
