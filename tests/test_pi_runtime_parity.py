from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
CODEX_SKILL = HOME / ".codex" / "skills" / "orchestrate"
PI_SKILL = HOME / ".pi" / "agent" / "skills" / "orchestrate"


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
            manifest = self.release.build_manifest(skill, 119)
            self.assertTrue({"runtime-codex.md", "runtime-claude.md", "runtime-pi.md"} <= set(manifest["documents"]))
            expected = {
                path.relative_to(HOME).as_posix()
                for path in self.release.profile_paths(HOME)
                if path.is_file()
            }
            self.assertEqual(set(manifest["profiles"]), expected)
            self.assertIn(".codex/agents/wave-oracle.toml", manifest["profiles"])
            self.assertNotIn(".codex/agents/wave-reviewer.toml", manifest["profiles"])

    def test_profile_contracts_match_across_runtimes(self) -> None:
        for name in ("contract-planner", "wave-oracle", "wave-implementer"):
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

    def test_pi_profiles_keep_runtime_frontmatter_contract(self) -> None:
        for name in ("wave-oracle", "wave-implementer"):
            text = (HOME / ".pi" / "agent" / "agents" / f"{name}.md").read_text(encoding="utf-8")
            for key in ("model:", "thinking:", "tools:", "systemPromptMode:", "inheritProjectContext:", "inheritSkills:", "pipeline:"):
                self.assertIn(key, text)

    def test_role_profiles_and_bindings_are_v119(self) -> None:
        for runtime, suffix, root in (("codex", ".toml", HOME / ".codex" / "agents"), ("claude", ".md", HOME / ".claude" / "agents"), ("pi", ".md", HOME / ".pi" / "agent" / "agents")):
            for role in ("wave-oracle", "wave-implementer"):
                text = (root / f"{role}{suffix}").read_text(encoding="utf-8").lower()
                self.assertIn("slice-ready", text)
                self.assertIn("exact", text)
                self.assertIn("sha", text)
            self.assertFalse((root / f"wave-reviewer{suffix}").exists(), runtime)
        codex = (CODEX_SKILL / "runtime-codex.md").read_text(encoding="utf-8").lower()
        self.assertIn("two persistent native role agents", codex)
        self.assertIn("no simulated queue", codex)

    def test_pi_lazy_pipeline_wording_is_direct_and_not_duplicated(self) -> None:
        pi = " ".join((PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split())
        lazy_creation_rule = (
            "Root lazily declares the wave-implementer pipeline bound to the `wave-implementer` "
            "agent after the first Contract merge, then enqueues the first real Implementation task."
        )
        self.assertIn("generic pipeline", pi.lower())
        self.assertEqual(pi.count(lazy_creation_rule), 1)
        self.assertIn("## Dual-role generic pipelines and terminal handoff", pi)
        self.assertIn("Root controls dependency depth", pi)
        self.assertNotIn("Implementation pipeline is lazy", pi)
        self.assertNotIn("pipeline lazily", pi)
        self.assertNotIn("pipeline from the first real Implementation task", pi)

    def test_runtime_core_has_no_binding_authority(self) -> None:
        source = (CODEX_SKILL / "scripts" / "_orchestrate" / "v119_core.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?i)pi-subagents|queue.{0,80}(write|persist|file)")

    def test_doctor_detects_shipped_profile_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "home" / ".codex" / "skills" / "orchestrate"
            skill.parent.mkdir(parents=True)
            import shutil
            shutil.copytree(CODEX_SKILL, skill)
            profile = root / "home" / ".codex" / "agents" / "wave-oracle.toml"
            profile.parent.mkdir(parents=True)
            import shutil
            shutil.copy2(HOME / ".codex" / "agents" / "wave-oracle.toml", profile)
            profile.write_text(profile.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")
            result = self.release.verify_release(skill)
            self.assertFalse(result["ok"])
            self.assertTrue(any("wave-oracle" in error for error in result["errors"]))

    def test_always_resident_rules_match_and_fit_budget(self) -> None:
        self.assertEqual((HOME / ".codex" / "AGENTS.md").read_bytes(), (HOME / ".pi" / "agent" / "APPEND_SYSTEM.md").read_bytes())
        skill = (CODEX_SKILL / "SKILL.md").read_text(encoding="utf-8")
        source = (HOME / ".pi" / "agent" / "APPEND_SYSTEM.md").read_text(encoding="utf-8")
        self.assertEqual(" ".join(skill[skill.index("\n1."):skill.index("\n## Workflow")].split()), " ".join(source[source.index("\n1."):].split()))
        self.assertTrue(all(path.stat().st_size <= 16_384 for path in CODEX_SKILL.rglob("*.md")))


if __name__ == "__main__":
    unittest.main()
