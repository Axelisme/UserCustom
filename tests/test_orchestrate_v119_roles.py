from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
SKILL = HOME / ".codex" / "skills" / "orchestrate"
PI_SKILL = HOME / ".pi" / "agent" / "skills" / "orchestrate"
CODEX_SKILL = SKILL


class V119RoleRuntimeContractTests(unittest.TestCase):
    """Oracle-owned package contracts for the dual-role runtime seam.

    These assertions deliberately consume shipped profiles and runtime documents rather
    than importing runtime helpers.  Implementer-local production choices cannot weaken
    this acceptance surface; the expected red state is a missing role/runtime contract.
    """

    role_profiles = {
        "codex": HOME / ".codex" / "agents",
        "claude": HOME / ".claude" / "agents",
        "pi": HOME / ".pi" / "agent" / "agents",
    }

    def read_profile(self, runtime: str, role: str) -> str:
        suffix = {"codex": ".toml", "claude": ".md", "pi": ".md"}[runtime]
        path = self.role_profiles[runtime] / f"{role}{suffix}"
        self.assertTrue(path.is_file(), f"missing shipped {runtime} profile: {path}")
        return path.read_text(encoding="utf-8")

    def test_wave_oracle_is_shipped_and_pi_pipeline_capable(self) -> None:
        for runtime in self.role_profiles:
            with self.subTest(runtime=runtime):
                text = self.read_profile(runtime, "wave-oracle")
                self.assertIn("wave-oracle", text)
                self.assertRegex(
                    text,
                    r"(?is)public interface.*contract tests|contract tests.*public interface",
                )
                self.assertIn("fixtures", text.lower())
                if runtime == "pi":
                    frontmatter = text.split("---", 2)[1]
                    self.assertRegex(frontmatter, r"(?m)^pipeline:\s*true\s*$")
                    self.assertRegex(frontmatter, r"(?m)^async:\s*true\s*$")

    def test_role_profiles_define_runtime_continuation_without_undefined_fallback(self) -> None:
        for runtime in self.role_profiles:
            for role in ("wave-oracle", "wave-implementer"):
                with self.subTest(runtime=runtime, role=role):
                    normalized = " ".join(self.read_profile(runtime, role).split())
                    self.assertRegex(
                        normalized,
                        r"(?i)Pi (?:frontmatter|metadata).{0,100}pipeline eligibility"
                        r".{0,140}Codex.{0,60}Claude.{0,140}native role continuation",
                    )
                    self.assertNotIn("ordinary fallback", normalized.lower())
                    self.assertNotIn("pipeline_capable", normalized)

    def test_revised_implementer_preserves_contract_surface_and_may_overlap_production(self) -> None:
        required = (
            "contract tests",
            "fixtures",
            "test adapters",
            "immutable",
            "production paths",
            "overlap",
        )
        for runtime in self.role_profiles:
            with self.subTest(runtime=runtime):
                text = self.read_profile(runtime, "wave-implementer").lower()
                for phrase in required:
                    self.assertIn(phrase, text)
                self.assertRegex(text, r"cannot|must not|do not")

    def test_ready_commits_and_terminal_handoffs_use_the_v119_git_contract(self) -> None:
        for runtime in self.role_profiles:
            for role, milestone, role_trailer in (
                ("wave-oracle", r"(?:Contract|Oracle-ready) commits?", "Role: oracle"),
                (
                    "wave-implementer",
                    r"(?:ready|Implementation-ready) commits?",
                    "Role: implementation",
                ),
            ):
                with self.subTest(runtime=runtime, role=role):
                    text = " ".join(self.read_profile(runtime, role).split())
                    self.assertRegex(text, rf"(?i){milestone}.{{0,360}}trailers?")
                    for trailer in (
                        "Wave: <wave-id>", "Slice: <slice-id>", role_trailer
                    ):
                        self.assertIn(trailer, text)
                    self.assertNotIn("seam-ready", text.lower())
                    self.assertNotRegex(
                        text,
                        r"(?i)commit trailers?\s*\([^)]*\bSHA\b",
                        "the exact SHA belongs to terminal slice-ready, not its own commit",
                    )
                    self.assertNotRegex(
                        text,
                        r"(?i)(?:SHA:\s*<commit-sha>.{0,80}(?:commit )?trailer"
                        r"|(?:commit )?trailer.{0,80}SHA:\s*<commit-sha>)",
                    )

        runtime_bindings = {
            "codex": SKILL / "runtime-codex.md",
            "pi": PI_SKILL / "runtime-pi.md",
            "claude": SKILL / "runtime-claude.md",
        }
        for runtime, path in runtime_bindings.items():
            with self.subTest(runtime_binding=runtime):
                text = " ".join(path.read_text(encoding="utf-8").split())
                self.assertNotIn("seam-ready", text.lower())
                self.assertNotRegex(text, r"(?i)commit trailers?\s*\([^)]*\bSHA\b")
                self.assertNotRegex(
                    text,
                    r"(?i)(?:SHA:\s*<commit-sha>.{0,80}(?:commit )?trailer"
                    r"|(?:commit )?trailer.{0,80}SHA:\s*<commit-sha>)",
                )

        codex = " ".join(runtime_bindings["codex"].read_text(encoding="utf-8").split())
        degraded = codex[codex.lower().index("degraded v1 transport") :]
        for trailer in ("Wave: <wave-id>", "Slice: <slice-id>"):
            self.assertIn(trailer, degraded)
        self.assertRegex(
            degraded,
            r"Role: (?:<role>|oracle.{0,80}implementation|implementation.{0,80}oracle)",
        )
        self.assertRegex(
            degraded,
            r"(?i)(?:terminal.{0,240}(?:full exact|exact 40-character|exact commit) SHA"
            r"|(?:full exact|exact 40-character|exact commit) SHA.{0,240}terminal)",
        )

    def test_slice_ready_is_terminal_and_carries_slice_and_exact_sha(self) -> None:
        surfaces = {
            "oracle-codex": self.read_profile("codex", "wave-oracle"),
            "oracle-claude": self.read_profile("claude", "wave-oracle"),
            "oracle-pi": self.read_profile("pi", "wave-oracle"),
            "implementer-codex": self.read_profile("codex", "wave-implementer"),
            "implementer-claude": self.read_profile("claude", "wave-implementer"),
            "implementer-pi": self.read_profile("pi", "wave-implementer"),
            "codex-binding": (SKILL / "runtime-codex.md").read_text(encoding="utf-8"),
            "pi-binding": (PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8"),
        }
        for name, text in surfaces.items():
            with self.subTest(surface=name):
                normalized = " ".join(text.lower().split())
                self.assertIn("slice-ready", normalized)
                self.assertRegex(normalized, r"slice-ready.{0,180}slice")
                self.assertRegex(normalized, r"slice-ready.{0,240}(sha|commit)")
                self.assertRegex(normalized, r"terminal.{0,160}(turn|handoff|signal|response)")
                self.assertRegex(
                    normalized,
                    r"(?:immediate(ly)? (?:end|complete|completion)|ends? (?:this )?turn immediate)",
                )

    def test_interactive_pi_root_does_not_wait_on_role_pipeline_completion(self) -> None:
        text = " ".join((PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split())
        self.assertRegex(
            text,
            r"(?i)interactive Pi Root.{0,120}(?:does not|do not|must not|should not|never)"
            r".{0,120}(?:`subagent_wait`.{0,40}`wait_subagent`|"
            r"`wait_subagent`.{0,40}`subagent_wait`).{0,120}"
            r"(?:merely|only|just).{0,40}wait.{0,100}(?:pipeline|role).{0,60}completion",
        )

    def test_interactive_pi_root_ends_turn_for_completion_notification(self) -> None:
        text = " ".join((PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split())
        self.assertRegex(
            text,
            r"(?i)no independent local work remains.{0,120}"
            r"(?:Root )?(?:should )?ends? (?:the|its) turn.{0,180}"
            r"(?:Pi(?:'s)? )?subagent completion notification.{0,80}wakes? (?:the )?session",
        )

    def test_active_pi_goal_mode_yields_for_named_pending_completion(self) -> None:
        text = " ".join((PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split())
        self.assertRegex(
            text,
            r"(?i)active goal(?:-mode| mode) session.{0,120}`yield_goal`.{0,180}"
            r"reason.{0,120}pending.{0,80}(?:pipeline|role).{0,60}completion",
        )

    def test_pi_explicit_wait_exception_is_limited_to_noninteractive_runs(self) -> None:
        text = (PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8")
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
        self.assertTrue(
            any(
                "headless" in sentence.lower()
                and "run-to-completion" in sentence.lower()
                and "wait" in sentence.lower()
                and any(
                    limit in sentence.lower()
                    for limit in ("only", "reserve", "exception")
                )
                for sentence in sentences
            ),
            "explicit waiting must be limited to the headless/run-to-completion exception",
        )

    def test_pi_binds_roles_to_lazy_generic_pipelines_and_root_depth(self) -> None:
        text = " ".join((PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split())
        lazy_creation_rule = (
            "Root lazily creates and attaches the wave-implementer pipeline from the first "
            "real Implementation task after the first Contract merge."
        )
        self.assertEqual(
            text.count(lazy_creation_rule),
            1,
            "Pi must state the lazy Implementation pipeline rule once in direct Root wording",
        )
        self.assertEqual(
            re.findall(r"\b(?:lazy|lazily)\b", text, re.IGNORECASE),
            ["lazily"],
            "Pi must express lazy Implementation creation only once, in the required sentence",
        )
        self.assertIn("## Dual-role generic pipelines and terminal handoff", text)
        self.assertIn(
            "Root creates and attaches the wave-oracle pipeline from the real C0 task.",
            text,
        )
        self.assertIn("Root controls dependency depth", text)
        self.assertIn(
            "After emitting the terminal `slice-ready` handoff, the role immediately ends "
            "its turn and makes no further worktree changes.",
            text,
        )
        self.assertNotIn("Implementation pipeline is lazy", text)
        self.assertNotIn("pipeline lazily", text)
        self.assertNotIn("Create the / the Implementation pipeline", text)
        self.assertNotIn("followed by immediately end this turn", text)
        self.assertRegex(text, r"(?i)oracle.{0,180}(generic )?pipeline")
        self.assertRegex(text, r"Root.{0,180}(dependenc|queue).{0,180}(depth|placement)")
        self.assertNotRegex(text, r"\broot\b.{0,180}(dependenc|queue).{0,180}(depth|placement)")
        self.assertRegex(text, r"(?i)C0.{0,180}(oracle|pipeline)")
        self.assertRegex(text, r"(?i)generic pipeline lifecycle|pipeline lifecycle")
        self.assertRegex(text, r"(?i)pi-subagents.{0,180}(lifecycle|pipeline)")

    def test_codex_uses_two_persistent_native_role_agents_without_queue_emulation(self) -> None:
        text = " ".join((SKILL / "runtime-codex.md").read_text(encoding="utf-8").split())
        self.assertIn("wave-oracle", text)
        self.assertIn("wave-implementer", text)
        self.assertRegex(text, r"(?i)two persistent native (role )?agents")
        self.assertRegex(text, r"(?i)native (messag|follow.?up|continuation)")
        self.assertRegex(text, r"(?i)v1.{0,180}v2|v2.{0,180}v1")
        self.assertRegex(text, r"(?i)(no|without|never).{0,80}(simulated|durable).{0,80}queue")
        self.assertRegex(text, r"(?i)plan.{0,180}git|git.{0,180}plan")
        self.assertRegex(
            text,
            r"(?i)degraded.{0,220}terminal (?:output|response).{0,180}exact (?:commit )?SHA",
        )
        self.assertNotRegex(text, r"(?i)commit trailers?\s*\([^)]*\bSHA\b")

    def test_worktree_identity_helper_name_reveals_its_responsibility(self) -> None:
        sources = (
            CODEX_SKILL / "scripts" / "_orchestrate" / "v119_core.py",
            PI_SKILL / "scripts" / "_orchestrate" / "v119_core.py",
        )
        for source_path in sources:
            with self.subTest(source=source_path):
                tree = ast.parse(source_path.read_text(encoding="utf-8"))
                function_names = {
                    node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                }
                self.assertIn("_worktree_identity", function_names)
                self.assertNotIn("_ids", function_names)

    def test_plan_and_git_are_recovery_authority_not_runtime_state(self) -> None:
        for path in (SKILL / "runtime-codex.md", PI_SKILL / "runtime-pi.md"):
            with self.subTest(path=path):
                text = " ".join(path.read_text(encoding="utf-8").split())
                self.assertRegex(text, r"(?i)(restart|compaction|recovery).{0,220}(plan|git)")
                self.assertRegex(text, r"(?i)(plan|git).{0,220}(recover|pending|position|continuation)")
                self.assertNotRegex(text, r"(?i)(write|persist|maintain).{0,80}(queue|runtime state) file")

    def test_orchestrate_core_has_no_runtime_binding_or_pipeline_authority(self) -> None:
        source = (SKILL / "scripts" / "_orchestrate" / "v119_core.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported |= {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertNotIn("pipeline", imported)
        self.assertNotIn("runtime", imported)
        self.assertNotRegex(source, r"(?i)pi-subagents|codex|claude|pipeline")
        self.assertNotRegex(source, r"(?i)queue.{0,80}(write|persist|file)")

    def test_pi_runtime_links_lifecycle_authority_instead_of_copying_it(self) -> None:
        text = (PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8")
        links = re.findall(r"\[[^]]*(?:pipeline|lifecycle)[^]]*\]\(([^)]+)\)", text, re.I)
        self.assertTrue(
            any("pi-subagents" in target or "pipeline" in target for target in links),
            "Pi binding must link generic pi-subagents pipeline lifecycle authority",
        )
        normalized = " ".join(text.split())
        self.assertRegex(
            normalized,
            r"(?i)(?:lifecycle|attach|restore|resume|close).{0,220}(?:pi-subagents|generic pipeline)",
        )
        self.assertRegex(
            normalized,
            r"(?i)(?:pi-subagents|generic pipeline).{0,220}(?:lifecycle|attach|restore|resume|close)",
        )
        # These headings are part of the immutable parity seam; lifecycle authority
        # must be established by linkage/content, never by deleting shared sections.
        for heading in (
            "## Activation and leases",
            "## Runtime budgets",
            "## Milestones and flow control",
        ):
            self.assertIn(heading, text)


if __name__ == "__main__":
    unittest.main()
