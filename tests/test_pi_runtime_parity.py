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
                manifest = self.release.build_manifest(skill, 113)
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
                self.assertGreaterEqual(len(manifest["profiles"]), 35)

    def test_profile_contracts_match_across_runtimes(self) -> None:
        names = ("contract-planner", "wave-implementer", "wave-reviewer")
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
                for text in (codex, claude, pi):
                    if name == "wave-reviewer":
                        self.assertIn("Root creates and proves each immutable exact-SHA review job/worktree before dispatch", text)
                        self.assertIn("supplies its job cwd in the dispatch", text)
                        self.assertIn("Never create, advance, retarget, or clean", text)
                        self.assertNotIn("Open your own detached checkout", text)
                        self.assertNotIn("review checkout <sha>", text)
                    if name == "contract-planner":
                        self.assertIn("every dependency- and authority-valid ready slice", text)
                        self.assertIn("arbitrary ready depth", text)
                        self.assertIn("root owns runtime queue placement", text)
                        self.assertIn("priority, and timing", text)
                        self.assertIn("may release any dependency- and authority-valid ready depth", text)
                        self.assertIn("there is no global one-deep queue", text)
                        self.assertIn("never mutates runtime queue", text)
                        for stale in ("next ready slice", "never deeper", "stock goes stale", "releases waves one at a time"):
                            self.assertNotIn(stale, text)

    def test_pi_profiles_keep_runtime_frontmatter_contract(self) -> None:
        for name in ("contract-planner", "wave-implementer", "wave-reviewer"):
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

    def test_pi_orchestrate_profiles_encode_stable_launch_defaults(self) -> None:
        for name in ("wave-implementer", "wave-reviewer", "integration-reviewer"):
            text = (
                HOME / ".pi" / "agent" / "agents" / f"{name}.md"
            ).read_text(encoding="utf-8")
            with self.subTest(profile=name):
                self.assertIn("defaultContext: fresh", text)
                self.assertIn("async: true", text)
                self.assertIn('acceptance: {"level":"none"', text)
                self.assertIn("Orchestrate owns authoritative acceptance", text)

    def test_pi_runtime_documents_profile_backed_launch_presets(self) -> None:
        text = (PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        for phrase in (
            "## Recommended launch presets",
            "recipes, not a `preset` tool field",
            "`lane-writer`",
            "`exact-sha-review`",
            "`read-only-evidence`",
            "Do not apply these presets to generic Pi delegation",
            "do not point runtime `output` at the canonical receipt path",
            "same-identity continuation is not a fresh launch preset",
            "cwd, frozen base or subject SHA, write or review scope",
        ):
            self.assertIn(phrase, normalized)
        preset_section = text[
            text.index("## Recommended launch presets") :
            text.index("## Activation and leases")
        ]
        self.assertGreaterEqual(preset_section.count('"artifacts": false'), 3)
        self.assertNotIn('"turnBudget"', preset_section)
        self.assertNotIn('"toolBudget"', preset_section)
        self.assertNotIn('"worktree": true', preset_section)

    def test_pi_runtime_documents_yield_goal_policy(self) -> None:
        text = (PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        for phrase in (
            "## Pi goal yield policy",
            "active interactive `pi-goal` session",
            "`yield_goal({ reason })`",
            "no blocking tool remains in progress",
            "no synchronous autonomous root work can make progress",
            "next prerequisite requires a future agent turn",
            "async child or provider completion",
            "future ordinary user reply",
            "another external result",
            "Do not yield while autonomous work remains",
            "blocking `ask_user_question`",
            "yield_goal` is terminal",
            "sole final tool action",
            "subagent_wait` for explicit run-to-completion or headless cases",
            "Never claim that Enter wakes `subagent_wait`",
            "Pi-specific",
            "does not change generic runtime defaults or `pi-subagents` tool semantics",
        ):
            self.assertIn(phrase, normalized)

    def test_pi_goal_local_package_declaration_is_unique_and_resolves_to_checkout(self) -> None:
        settings_path = HOME / ".pi" / "agent" / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        packages = settings.get("packages")
        self.assertIsInstance(packages, list)
        local_entry = "../../Documents/VSCode/Typescript/pi-goal"
        self.assertEqual(packages.count(local_entry), 1)
        self.assertFalse(any(package == "npm:pi-goal" for package in packages))
        resolved = (Path("/home/axel/.pi/agent") / local_entry).resolve()
        self.assertEqual(
            resolved, Path("/home/axel/Documents/VSCode/Typescript/pi-goal")
        )

    def test_always_resident_iron_rules_match(self) -> None:
        codex = (HOME / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        pi = (HOME / ".pi" / "agent" / "APPEND_SYSTEM.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(codex, pi)

    def test_shipped_iron_rule_matches_pi_source_numbered_rules(self) -> None:
        skill = (PI_SKILL / "SKILL.md").read_text(encoding="utf-8")
        source = (HOME / ".pi" / "agent" / "APPEND_SYSTEM.md").read_text(encoding="utf-8")
        skill_rules = skill[skill.index("\n1.") : skill.index("\n## Pipeline model")]
        source_rules = source[source.index("\n1.") :]
        self.assertEqual(" ".join(skill_rules.split()), " ".join(source_rules.split()))

    def test_wave_roster_models_and_legacy_names(self) -> None:
        self.assertFalse((HOME / ".pi" / "agent" / "agents" / "implementer.md").exists())
        self.assertFalse((HOME / ".pi" / "agent" / "agents" / "reviewer.md").exists())
        wave_reviewer = (HOME / ".pi" / "agent" / "agents" / "wave-reviewer.md").read_text(encoding="utf-8")
        self.assertIn('name: "wave-reviewer"', wave_reviewer)
        self.assertIn('model: "openai-codex/gpt-5.6-sol"', wave_reviewer)
        self.assertIn('thinking: "low"', wave_reviewer)
        integration = (HOME / ".pi" / "agent" / "agents" / "integration-reviewer.md").read_text(encoding="utf-8")
        self.assertIn('model: "openai-codex/gpt-5.6-sol"', integration)
        self.assertIn('thinking: "high"', integration)

    def test_python_specialists_use_dispatch_facts_not_repo_constants(self) -> None:
        targets = (
            HOME / ".pi" / "agent" / "agents" / "impl-detail-planner.md",
            HOME / ".pi" / "agent" / "agents" / "plan-item-implementer.md",
            HOME / ".pi" / "agent" / "agents" / "python-bug-investigator.md",
            HOME / ".codex" / "agents" / "impl-detail-planner.toml",
            HOME / ".codex" / "agents" / "plan-item-implementer.toml",
            HOME / ".codex" / "agents" / "python-bug-investigator.toml",
            HOME / ".codex" / "agents" / "python-module-reviewer.toml",
            HOME / ".claude" / "agents" / "impl-detail-planner.md",
            HOME / ".claude" / "agents" / "plan-item-implementer.md",
            HOME / ".claude" / "agents" / "python-bug-investigator.md",
            HOME / ".claude" / "agents" / "python-module-reviewer.md",
        )
        forbidden = ("ZCU", "QICK", "zcu_tools", "lib/zcu_tools", "tests/gui", ".venv/bin/python", "/home/axel/.codex/agent-memory")
        for path in targets:
            text = path.read_text(encoding="utf-8")
            with self.subTest(profile=path):
                self.assertIn("Dispatch-provided facts", text)
                for term in forbidden:
                    self.assertNotIn(term, text)

    def test_pi_routing_and_cleanup_contract(self) -> None:
        text = " ".join((PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split())
        for phrase in (
            "orchestrate-specific user profiles",
            "builtins for generic delegation",
            "wave-ahead planning",
            "reconnaissance therefore default to fresh async launches",
            "collect, integrate, release, and landing",
            "never dispatched as children",
            "Foreground detach is a supervisor-wait transport state",
            "unrelated to a Git detached HEAD",
            'subagent({ action: "status", view: "fleet" })',
            "eligible cumulative frontier immediately",
            "not mandatory per slice",
            "second same-surface identity",
        ):
            self.assertIn(phrase, text)
        cleanup = text[text.index("## Cleanup lease check") : text.index("## Cumulative review scheduling")]
        self.assertNotIn('subagent({ action: "list" })', cleanup)

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
            "stop it and observe terminal state before cleanup",
            "compaction summary is not a handoff contract",
        ):
            self.assertIn(phrase, text)

    def test_pi_runtime_binding_matches_across_skill_overlays(self) -> None:
        self.assertEqual(
            (CODEX_SKILL / "runtime-pi.md").read_bytes(),
            (PI_SKILL / "runtime-pi.md").read_bytes(),
        )

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
        for name in self.release.PROFILE_NAMES:
            codex = root / "home" / ".codex" / "agents" / f"{name}.toml"
            claude = root / "home" / ".claude" / "agents" / f"{name}.md"
            pi = root / "home" / ".pi" / "agent" / "agents" / f"{name}.md"
            codex.parent.mkdir(parents=True, exist_ok=True)
            claude.parent.mkdir(parents=True, exist_ok=True)
            pi.parent.mkdir(parents=True, exist_ok=True)
            codex.write_text(
                f'name = "{name}"\ndeveloper_instructions = \'\'\'orders\'\'\'\n',
                encoding="utf-8",
            )
            claude.write_text(f"---\nname: {name}\n---\n# {name}\n", encoding="utf-8")
            pi.write_text(f"---\nname: \\\"{name}\\\"\n---\n# {name}\n", encoding="utf-8")
        agent = root / "home" / ".pi" / "agent" / "agents" / "wave-implementer.md"
        agent.write_text(
            "---\nname: wave-implementer\nmodel: tuned-model\nthinking: high\n"
            "fallbackModels:\n  - fallback-a\n  - fallback-b\n"
            "tools: read, write\nsystemPromptMode: replace\n---\n# Wave Implementer\n",
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
            'name = "wave-implementer"\n'
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
            agent = root / "home" / ".pi" / "agent" / "agents" / "wave-implementer.md"
            original = agent.read_text(encoding="utf-8")

            agent.write_text(original.replace("tools: read, write", "tools: read"), encoding="utf-8")
            result = self.release.verify_release(skill)
            self.assertFalse(result["ok"])
            self.assertIn("hash mismatch: .pi/agent/agents/wave-implementer.md", result["errors"])

            tuned = original.replace("model: tuned-model", "model: another-model")
            tuned = tuned.replace("  - fallback-a\n  - fallback-b", "  - fallback-c")
            agent.write_text(tuned, encoding="utf-8")
            self.assertTrue(self.release.verify_release(skill)["ok"])

    def test_doctor_detects_every_shipped_profile_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = self.make_pi_release_fixture(root)
            for name, relative in (
                ("integration-reviewer", Path(".pi/agent/agents/integration-reviewer.md")),
                ("python-bug-investigator", Path(".pi/agent/agents/python-bug-investigator.md")),
            ):
                path = root / "home" / relative
                path.write_text(path.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
                result = self.release.verify_release(skill)
                self.assertFalse(result["ok"], name)
                self.assertIn(f"hash mismatch: {relative.as_posix()}", result["errors"])
                path.write_text(path.read_text(encoding="utf-8").removesuffix("tampered\n"), encoding="utf-8")

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
                    ".pi/agent/agents/wave-implementer.md",
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
