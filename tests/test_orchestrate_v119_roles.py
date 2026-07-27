from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
SKILL = HOME / ".codex" / "skills" / "orchestrate"
PI_SKILL = HOME / ".pi" / "agent" / "skills" / "orchestrate"
ROLE_PROFILES = {
    "codex": (HOME / ".codex" / "agents", ".toml"),
    "claude": (HOME / ".claude" / "agents", ".md"),
    "pi": (HOME / ".pi" / "agent" / "agents", ".md"),
}


class V128RoleRuntimeContractTests(unittest.TestCase):
    """Contract for native Codex/Claude roles and the Pi-only pipeline adapter."""

    def read_profile(self, runtime: str, role: str) -> str:
        root, suffix = ROLE_PROFILES[runtime]
        path = root / f"{role}{suffix}"
        self.assertTrue(path.is_file(), f"missing shipped {runtime} profile: {path}")
        return path.read_text(encoding="utf-8")

    def test_role_profiles_define_the_public_contract_surface(self) -> None:
        for runtime in ROLE_PROFILES:
            with self.subTest(runtime=runtime):
                text = self.read_profile(runtime, "wave-oracle").lower()
                for phrase in ("public interface", "contract tests", "fixtures", "test adapters"):
                    self.assertIn(phrase, text)

    def test_pi_frontmatter_is_the_only_pipeline_eligibility_surface(self) -> None:
        for runtime in ("codex", "claude"):
            for role in ("wave-oracle", "wave-implementer"):
                with self.subTest(runtime=runtime, role=role):
                    self.assertNotRegex(
                        self.read_profile(runtime, role),
                        r"(?m)^pipeline:\s*true\s*$",
                    )
        for role in ("wave-oracle", "wave-implementer"):
            with self.subTest(runtime="pi", role=role):
                self.assertRegex(
                    self.read_profile("pi", role),
                    r"(?m)^pipeline:\s*true\s*$",
                )

    def test_codex_and_claude_use_native_lifecycle_without_pipeline_emulation(self) -> None:
        for runtime, binding in (
            ("codex", SKILL / "runtime-codex.md"),
            ("claude", SKILL / "runtime-claude.md"),
        ):
            text = " ".join(binding.read_text(encoding="utf-8").split()).lower()
            with self.subTest(runtime=runtime):
                self.assertIn("native", text)
                self.assertIn("continuation", text)
                self.assertNotIn("pipelinemanager", text)
                self.assertNotIn("generic pipeline", text)

    def test_pi_binding_names_pipelinemanager_as_its_runtime_adapter(self) -> None:
        text = " ".join((PI_SKILL / "runtime-pi.md").read_text(encoding="utf-8").split())
        self.assertIn("PipelineManager", text)
        self.assertIn("pipeline capability", text.lower())
        self.assertIn("attach", text.lower())
        self.assertIn("resume", text.lower())
        self.assertIn("close", text.lower())

    def test_ready_handoff_is_terminal_and_carries_slice_and_exact_sha(self) -> None:
        for runtime, (root, suffix) in ROLE_PROFILES.items():
            for role in ("wave-oracle", "wave-implementer"):
                with self.subTest(runtime=runtime, role=role):
                    text = " ".join(self.read_profile(runtime, role).split()).lower()
                    self.assertIn("slice-ready", text)
                    self.assertIn("slice", text)
                    self.assertIn("exact", text)
                    self.assertIn("sha", text)
                    self.assertIn("immediately", text)
                    self.assertIn("end", text)

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
        self.assertNotRegex(source, r"(?i)pi-subagents|codex|claude|pipelinemanager")


if __name__ == "__main__":
    unittest.main()
