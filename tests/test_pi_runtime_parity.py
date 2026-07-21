from __future__ import annotations

import argparse
from importlib import import_module
import json
import subprocess
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
        return import_module("_orchestrate.release")
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
            with self.subTest(skill=skill):
                manifest = self.release.build_manifest(skill, 108)
                self.assertTrue(
                    {"runtime-codex.md", "runtime-claude.md", "runtime-pi.md"}
                    <= set(manifest["documents"])
                )
                self.assertEqual(
                    set(manifest["profiles"]),
                    {
                        ".codex/agents/contract-planner.toml",
                        ".codex/agents/implementer.toml",
                        ".codex/agents/reviewer.toml",
                        ".claude/agents/contract-planner.md",
                        ".claude/agents/implementer.md",
                        ".claude/agents/reviewer.md",
                        ".pi/agent/APPEND_SYSTEM.md",
                        ".pi/agent/agents/contract-planner.md",
                        ".pi/agent/agents/implementer.md",
                        ".pi/agent/agents/reviewer.md",
                    },
                )

    def test_profile_contracts_match_across_runtimes(self) -> None:
        names = ("contract-planner", "implementer", "reviewer")
        for name in names:
            codex = (HOME / ".codex" / "agents" / f"{name}.toml").read_text(
                encoding="utf-8"
            )
            claude = (HOME / ".claude" / "agents" / f"{name}.md").read_text(
                encoding="utf-8"
            )
            pi = (HOME / ".pi" / "agent" / "agents" / f"{name}.md").read_text(
                encoding="utf-8"
            )
            with self.subTest(profile=name):
                bodies = {
                    self.release.normalized_sha256(
                        self.release.profile_standing_orders(text, suffix)
                    )
                    for text, suffix in ((codex, ".toml"), (claude, ".md"), (pi, ".md"))
                }
                self.assertEqual(len(bodies), 1)

    def test_pi_profiles_keep_runtime_frontmatter_contract(self) -> None:
        for name in ("contract-planner", "implementer", "reviewer"):
            text = (
                HOME / ".pi" / "agent" / "agents" / f"{name}.md"
            ).read_text(encoding="utf-8")
            with self.subTest(profile=name):
                for key in (
                    "model:",
                    "thinking:",
                    "tools:",
                    "systemPromptMode:",
                    "inheritProjectContext:",
                    "inheritSkills:",
                ):
                    self.assertIn(key, text)

    def test_always_resident_iron_rules_match(self) -> None:
        codex = (HOME / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        pi = (HOME / ".pi" / "agent" / "APPEND_SYSTEM.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(codex, pi)

    def test_pi_dispatch_binding_carries_explicit_ownership_baseline(self) -> None:
        text = " ".join(
            (PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split()
        )
        for phrase in (
            "explicit handoff baseline",
            "pre-existing user-owned dirty paths",
            "root-owned concurrent artifacts",
            "do not create one only to satisfy this transport rule",
            "set `artifacts: false`",
            "dirty the evidence tree",
            "Do not `resume` that child",
            "stop the runner before cleanup",
            "compaction summary is not a handoff contract",
        ):
            self.assertIn(phrase, text)

    def test_shared_skill_contracts_do_not_drift(self) -> None:
        for relative in (
            Path("dev-flow/SKILL.md"),
            Path("planning-with-files/SKILL.md"),
        ):
            with self.subTest(relative=relative):
                self.assertEqual(
                    (HOME / ".codex" / "skills" / relative).read_bytes(),
                    (HOME / ".pi" / "agent" / "skills" / relative).read_bytes(),
                )

    def make_pi_release_fixture(self, root: Path, version: int = 108) -> Path:
        skill = root / "home" / ".pi" / "agent" / "skills" / "orchestrate"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nskill_version: {version}\n---\n# Fixture\n", encoding="utf-8"
        )
        (skill / "runtime-pi.md").write_text("# Pi runtime\n", encoding="utf-8")
        append = root / "home" / ".pi" / "agent" / "APPEND_SYSTEM.md"
        append.parent.mkdir(parents=True, exist_ok=True)
        append.write_text("# Standing orders\n", encoding="utf-8")
        agent = root / "home" / ".pi" / "agent" / "agents" / "implementer.md"
        agent.parent.mkdir(parents=True)
        agent.write_text(
            "---\nname: implementer\nmodel: tuned-model\nthinking: high\n"
            "fallbackModels:\n  - fallback-a\n  - fallback-b\n"
            "tools: read, write\nsystemPromptMode: replace\n---\n# Implementer\n",
            encoding="utf-8",
        )
        manifest = self.release.build_manifest(skill, version)
        path = skill / "manifests" / f"{version}.json"
        path.parent.mkdir()
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return skill

    def test_aborted_release_recovery_reports_the_previous_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = self.make_pi_release_fixture(root)
            (skill / "manifests" / "108.json").unlink()
            result = self.release.command_release(
                argparse.Namespace(skill_dir=str(skill), version=108)
            )
            self.assertEqual(result["released_version"], 108)
            self.assertEqual(result["from_version"], 107)

    def test_doctor_detects_pi_runtime_and_standing_order_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = self.make_pi_release_fixture(root)
            self.assertTrue(self.release.verify_release(skill)["ok"])

            runtime = skill / "runtime-pi.md"
            runtime.write_text("# tampered runtime\n", encoding="utf-8")
            result = self.release.verify_release(skill)
            self.assertFalse(result["ok"])
            self.assertIn("hash mismatch: runtime-pi.md", result["errors"])

            runtime.write_text("# Pi runtime\n", encoding="utf-8")
            append = root / "home" / ".pi" / "agent" / "APPEND_SYSTEM.md"
            append.write_text("# tampered orders\n", encoding="utf-8")
            result = self.release.verify_release(skill)
            self.assertFalse(result["ok"])
            self.assertIn("hash mismatch: .pi/agent/APPEND_SYSTEM.md", result["errors"])

    def test_toml_contract_parsing_ignores_tuning_without_hiding_transport(self) -> None:
        original = (
            'name = "implementer"\n'
            'fallbackModels = [\n  "model[variant", # comment with ]\n]\n'
            'tools = "read"\n'
            "developer_instructions = '''orders'''\n"
        )
        tuning_change = original.replace("model[variant", "other]variant")
        transport_change = original.replace('tools = "read"', 'tools = "write"')
        self.assertEqual(
            self.release.profile_contract(original, ".toml"),
            self.release.profile_contract(tuning_change, ".toml"),
        )
        self.assertNotEqual(
            self.release.profile_contract(original, ".toml"),
            self.release.profile_contract(transport_change, ".toml"),
        )

    def test_doctor_tracks_pi_transport_contract_but_ignores_tuning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = self.make_pi_release_fixture(root)
            agent = root / "home" / ".pi" / "agent" / "agents" / "implementer.md"
            original = agent.read_text(encoding="utf-8")

            agent.write_text(original.replace("tools: read, write", "tools: read"), encoding="utf-8")
            result = self.release.verify_release(skill)
            self.assertFalse(result["ok"])
            self.assertIn("hash mismatch: .pi/agent/agents/implementer.md", result["errors"])

            tuned = original.replace("model: tuned-model", "model: another-model")
            tuned = tuned.replace("  - fallback-a\n  - fallback-b", "  - fallback-c")
            agent.write_text(tuned, encoding="utf-8")
            self.assertTrue(self.release.verify_release(skill)["ok"])

    def test_missing_unshipped_pi_manifests_fall_back_to_full_reread(self) -> None:
        for old_version in range(99, 107):
            with self.subTest(old_version=old_version), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                subprocess.run(
                    ["git", "init", "-b", "task/demo"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                skill = self.make_pi_release_fixture(root)
                pin = root / ".agent_state" / "orchestrate" / "version-pin.json"
                pin.parent.mkdir(parents=True)
                pin.write_text(
                    json.dumps(
                        {
                            "skill_version": old_version,
                            "orchestrate_compat": old_version,
                        }
                    ),
                    encoding="utf-8",
                )
                result = self.release.command_pin_migrate(
                    argparse.Namespace(root=str(root), skill_dir=str(skill))
                )
                self.assertIsNone(result["delta"])
                self.assertIn("reread all documents", result["delta_note"])
                requirements = result["migration_requirements"]
                self.assertEqual(
                    requirements["reason"], "source-manifest-unavailable"
                )
                self.assertIn("SKILL.md", requirements["must_reread"])
                self.assertIn(
                    ".pi/agent/agents/implementer.md",
                    requirements["must_rebootstrap_profiles"],
                )
                self.assertEqual(
                    requirements["must_acknowledge_standing_orders"],
                    [".pi/agent/APPEND_SYSTEM.md"],
                )
                self.assertEqual(result["to_version"], 108)

    def test_cli_accepts_pi_runtime_filter(self) -> None:
        script = CODEX_SKILL / "scripts" / "orchestrate.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "diff",
                "107",
                "108",
                "--runtime",
                "pi",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["runtime"], "pi")
        self.assertTrue(
            all(path.startswith(".pi/") for path in payload["changed_profiles"])
        )
        self.assertTrue(
            all(
                not document["path"].startswith("runtime-")
                or document["path"] == "runtime-pi.md"
                for document in payload["changed_documents"]
            )
        )


if __name__ == "__main__":
    unittest.main()
