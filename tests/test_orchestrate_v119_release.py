from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
CODEX_SKILL = HOME / ".codex" / "skills" / "orchestrate"
PI_SKILL = HOME / ".pi" / "agent" / "skills" / "orchestrate"
CODEX_SCRIPT = CODEX_SKILL / "scripts" / "orchestrate.py"
SHIPPED_VERSION = int(
    re.search(r"(?m)^skill_version: (\d+)$", (CODEX_SKILL / "SKILL.md").read_text(encoding="utf-8")).group(1)
)


class OrchestrateV119ReleaseContractTests(unittest.TestCase):
    """Black-box/package Contract for the breaking v118 -> v119 contraction.

    This is intentionally authored against shipped files and the root CLI.  It must
    go red for stale v118 behavior, while import and fixture setup remain independent
    of the implementation that will perform the contraction.
    """

    retained_commands = {
        "worktree",
        "contract",
        "integration",
        "profile",
        "doctor",
        "diff",
        "pin",
        "release",
    }
    removed_commands = {
        "lane",
        "compose-base",
        "review",
        "land",
        "collect",
        "cleanup",
        "slice",
        "findings",
        "feedback",
        "revalidate",
        "reconcile",
        "wave",
    }
    legacy_modules = {
        "feedback.py",
        "findings.py",
        "landing.py",
        "lanes.py",
        "review.py",
    }
    legacy_documents = {
        "references/coordination.md",
        "references/publication-review.md",
    }
    legacy_tests = {
        "test_orchestrate_cli.py",
        "test_orchestrate_contract.py",
        "test_orchestrate_package.py",
        "test_orchestrate_phase3.py",
        "test_orchestrate_pwr08_wave_policy.py",
        "test_orchestrate_pwr09_review_lifecycle.py",
        "test_orchestrate_review_regressions.py",
        "test_orchestrate_v100_costs.py",
        "test_orchestrate_v101_interface.py",
        "test_orchestrate_v102_vocabulary.py",
        "test_orchestrate_v104_wave_boundary.py",
        "test_orchestrate_v105_findings_query.py",
        "test_orchestrate_v107_validated_unlanded.py",
        "test_orchestrate_v109_cleanup_safety.py",
        "test_orchestrate_v109_receipt_contract.py",
        "test_orchestrate_v115_tracers.py",
        "test_orchestrate_v96_sweep.py",
        "test_orchestrate_v99_review_pass.py",
    }

    @staticmethod
    def run_cli(*args: str, skill_dir: Path = CODEX_SKILL) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CODEX_SCRIPT), "--skill-dir", str(skill_dir), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def help_commands(text: str) -> set[str]:
        match = re.search(r"\{([^{}]+)\}", text)
        if match is None:
            raise AssertionError(f"root help has no command set:\n{text}")
        return set(match.group(1).split(","))

    def test_root_help_is_only_v119_workflow_and_retained_administration(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.help_commands(result.stdout), self.retained_commands)
        for command in self.removed_commands:
            self.assertNotIn(command, result.stdout)

    def test_v118_modules_tests_documents_and_role_references_are_gone(self) -> None:
        for skill in (CODEX_SKILL, PI_SKILL):
            with self.subTest(skill=skill):
                package = skill / "scripts" / "_orchestrate"
                present_modules = {path.name for path in package.glob("*.py")}
                self.assertTrue(
                    self.legacy_modules.isdisjoint(present_modules),
                    f"legacy modules remain in {skill}: {self.legacy_modules & present_modules}",
                )
                present_documents = {
                    path.relative_to(skill).as_posix()
                    for path in skill.rglob("*")
                    if path.is_file()
                }
                self.assertTrue(
                    self.legacy_documents.isdisjoint(present_documents),
                    f"legacy documents remain in {skill}: {self.legacy_documents & present_documents}",
                )
                stale_references = []
                for path in skill.rglob("*"):
                    if (
                        not path.is_file()
                        or "manifests" in path.parts
                        or "__pycache__" in path.parts
                        or path.suffix == ".pyc"
                    ):
                        continue
                    text = path.read_text(encoding="utf-8", errors="replace")
                    for term in ("wave-reviewer", "integration-reviewer"):
                        if term in text:
                            stale_references.append(f"{path.relative_to(skill)}:{term}")
                self.assertEqual(stale_references, [])

        present_tests = {path.name for path in (ROOT / "tests").glob("test_*.py")}
        self.assertTrue(
            self.legacy_tests.isdisjoint(present_tests),
            f"legacy tests remain: {self.legacy_tests & present_tests}",
        )

    def test_wave_oracle_is_shipped_and_wave_reviewer_is_not(self) -> None:
        for profile_root in (
            HOME / ".codex" / "agents",
            HOME / ".claude" / "agents",
            HOME / ".pi" / "agent" / "agents",
        ):
            with self.subTest(profile_root=profile_root):
                oracle = next(profile_root.glob("wave-oracle.*"), None)
                self.assertIsNotNone(oracle, f"missing wave-oracle under {profile_root}")
                self.assertFalse(any(profile_root.glob("wave-reviewer.*")))

    def test_shipped_skill_manifests_and_doctors_are_current(self) -> None:
        for skill in (CODEX_SKILL, PI_SKILL):
            with self.subTest(skill=skill):
                skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
                self.assertRegex(skill_text, rf"(?m)^skill_version: {SHIPPED_VERSION}$")
                manifest_path = skill / "manifests" / f"{SHIPPED_VERSION}.json"
                self.assertTrue(manifest_path.is_file(), f"missing manifest: {manifest_path}")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["skill_version"], SHIPPED_VERSION)
                self.assertEqual(manifest["orchestrate_compat"], SHIPPED_VERSION)

                script = skill / "scripts" / "orchestrate.py"
                result = subprocess.run(
                    [sys.executable, str(script), "doctor"],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertTrue(payload["ok"], payload)
                self.assertEqual(payload["skill_version"], SHIPPED_VERSION)
                self.assertEqual(payload["orchestrate_compat"], SHIPPED_VERSION)
                self.assertEqual(payload["errors"], [])

    def test_retained_markdown_documents_fit_the_single_read_budget(self) -> None:
        for skill in (CODEX_SKILL, PI_SKILL):
            for path in skill.rglob("*.md"):
                with self.subTest(path=path):
                    self.assertLessEqual(len(path.read_bytes()), 16_384)

    def test_pin_migrate_remains_a_retained_administration_command(self) -> None:
        result = self.run_cli("pin", "migrate", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--root", result.stdout)


if __name__ == "__main__":
    unittest.main()
