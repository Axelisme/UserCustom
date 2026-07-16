from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPT = SKILL / "scripts" / "orchestrate.py"
PLAN_SCRIPT = (
    ROOT / "home" / ".codex" / "skills" / "planning-with-files" / "scripts" / "plan.py"
)
REVIEWER = ROOT / "home" / ".codex" / "agents" / "reviewer.toml"


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        check=False,
        text=True,
        capture_output=True,
    )


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout.strip()


def initialize_repo(root: Path) -> str:
    git(root, "init", "-b", "task/demo")
    git(root, "config", "user.name", "Orchestrate Test")
    git(root, "config", "user.email", "orchestrate@example.invalid")
    (root / ".gitignore").write_text(".agent_state/\n", encoding="utf-8")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    git(root, "add", ".gitignore", "README.md")
    git(root, "commit", "-m", "base")
    return git(root, "rev-parse", "HEAD")


def write_packet(root: Path, payload: dict[str, object]) -> Path:
    path = root / "packet.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class OrchestrateCliTests(unittest.TestCase):
    def test_doctor_and_diff_use_release_manifests(self) -> None:
        doctor = run_cli("doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        payload = json.loads(doctor.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["skill_version"], 61)
        self.assertEqual(payload["profiles"], 6)
        manifest = json.loads(
            (SKILL / "manifests" / "61.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["release_delta"]["from_version"], 60)
        self.assertIn("SKILL.md", manifest["release_delta"]["changed_sections"])
        self.assertIn("SKILL.md", manifest["release_delta"]["must_reread"])

        diff = run_cli("diff", "51", "61", "--runtime", "codex")
        self.assertEqual(diff.returncode, 0, diff.stderr)
        payload = json.loads(diff.stdout)
        self.assertEqual(payload["compat"], [51, 61])
        self.assertEqual(payload["runtime"], "codex")
        self.assertIn("SKILL.md", payload["must_reread"])
        self.assertNotIn("runtime-claude.md", payload["must_reread"])
        self.assertNotIn(
            "runtime-claude.md",
            [document["path"] for document in payload["changed_documents"]],
        )
        self.assertTrue(
            all(name.startswith(".codex/") for name in payload["changed_profiles"])
        )
        self.assertTrue(payload["changed_documents"])

    def test_identity_reports_hashes_without_inference(self) -> None:
        result = run_cli(
            "identity",
            "--requested",
            "reviewer",
            "--effective",
            "generic_role_adapter",
            "--profile",
            str(REVIEWER),
            "--agent-id",
            "reviewer-1",
            "--writer-agent-id",
            "writer-1",
            "--require-different-identity",
            "--park-capability",
            "unknown",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["different_identity"])
        self.assertTrue(payload["requirements_satisfied"])
        self.assertEqual(payload["profile_manifest_version"], 61)
        self.assertEqual(payload["profile_compat"], 61)
        self.assertTrue(payload["profile_compat_matches_current"])
        self.assertEqual(payload["park_capability"], "unknown")
        self.assertEqual(len(payload["profile_sha256"]), 64)
        self.assertEqual(len(payload["standing_orders_sha256"]), 64)

    def test_lane_review_collect_cleanup_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = initialize_repo(root)

            created = run_cli(
                "lane",
                "create",
                "--root",
                str(root),
                "--task-id",
                "demo",
                "--lane",
                "core",
                "--base",
                base,
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            lane_payload = json.loads(created.stdout)
            lane = Path(lane_payload["path"])
            self.assertEqual(lane_payload["branch"], "agent/demo/core")
            self.assertTrue(lane_payload["clean"])

            (lane / "feature.txt").write_text("feature\n", encoding="utf-8")
            git(lane, "add", "feature.txt")
            git(lane, "commit", "-m", "feature")
            lane_sha = git(lane, "rev-parse", "HEAD")

            review = run_cli(
                "review",
                "checkout",
                lane_sha,
                "--root",
                str(root),
                "--label",
                "core",
            )
            self.assertEqual(review.returncode, 0, review.stderr)
            review_payload = json.loads(review.stdout)
            self.assertIsNone(review_payload["branch"])
            self.assertEqual(review_payload["head"], lane_sha)

            review_cleanup = run_cli(
                "review",
                "cleanup",
                "--root",
                str(root),
                "--worktree",
                review_payload["path"],
            )
            self.assertEqual(review_cleanup.returncode, 0, review_cleanup.stderr)

            collected = run_cli(
                "collect",
                "--root",
                str(root),
                "--task-ref",
                "task/demo",
                "--lane-ref",
                "agent/demo/core",
                "--expected-lane-sha",
                lane_sha,
                "--authorized-sha",
                lane_sha,
                "--review-kind",
                "root-spot",
            )
            self.assertEqual(collected.returncode, 0, collected.stderr)
            collected_payload = json.loads(collected.stdout)
            self.assertEqual(collected_payload["authorized_sha"], lane_sha)
            self.assertEqual(collected_payload["declared_review_kind"], "root-spot")
            self.assertFalse(collected_payload["verdict_inferred"])
            self.assertTrue((root / "feature.txt").is_file())

            cleanup = run_cli(
                "lane",
                "cleanup",
                "--root",
                str(root),
                "--task-ref",
                "task/demo",
                "--lane-ref",
                "agent/demo/core",
                "--worktree",
                str(lane),
            )
            self.assertEqual(cleanup.returncode, 0, cleanup.stderr)
            self.assertEqual(json.loads(cleanup.stdout)["absorption"], "ancestor")
            self.assertFalse(lane.exists())

    def test_status_combines_plan_and_observed_git(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_repo(root)
            initialized = subprocess.run(
                [
                    sys.executable,
                    str(PLAN_SCRIPT),
                    "--root",
                    str(root),
                    "init",
                    "demo",
                    "--goal",
                    "exercise status",
                    "--with-progress",
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)

            result = run_cli("status", "--root", str(root), "--task-id", "demo")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["task_id"], "demo")
            self.assertEqual(payload["remaining_phases"], ["Phase 1"])
            self.assertTrue(payload["worktrees"])
            self.assertIn("observed_at", payload)

    def test_review_checkout_rejects_unmanaged_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = initialize_repo(root)

            result = run_cli(
                "review",
                "checkout",
                base,
                "--root",
                str(root),
                "--worktree",
                str(root / "unmanaged-review"),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("must be below", result.stderr)
            self.assertFalse((root / "unmanaged-review").exists())

    def test_identity_recognizes_installed_profile_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "reviewer.toml"
            copied.write_bytes(REVIEWER.read_bytes())

            result = run_cli(
                "identity",
                "--requested",
                "reviewer",
                "--effective",
                "generic_role_adapter",
                "--profile",
                str(copied),
                "--agent-id",
                "reviewer-1",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["profile_manifest_version"], 61)
            self.assertEqual(payload["profile_compat"], 61)

    def test_milestone_lint_accepts_one_role_neutral_envelope(self) -> None:
        cases = {
            "writer": ("validated", "a" * 40),
            "reviewer": ("pass", "b" * 40),
            "planner": ("proposal", None),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for role, (outcome, subject_sha) in cases.items():
                payload: dict[str, object] = {
                    "event": "milestone",
                    "item_id": f"{role}-item",
                    "state": "terminal",
                    "outcome": outcome,
                    "evidence": "targeted evidence or artifact pointer",
                    "findings": [],
                    "next": "idle",
                }
                if subject_sha is not None:
                    payload["subject_sha"] = subject_sha
                path = root / f"{role}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")

                result = run_cli(
                    "milestone", "lint", "--role", role, "--input", str(path)
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                linted = json.loads(result.stdout)
                self.assertTrue(linted["ok"])
                self.assertFalse(linted["delivery_inferred"])

    def test_milestone_lint_rejects_old_duplicate_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet = write_packet(
                Path(temporary),
                {
                    "delivery_phase": "final",
                    "checkpoint_kind": "validated",
                    "sha": "a" * 40,
                },
            )

            result = run_cli(
                "milestone", "lint", "--role", "writer", "--input", str(packet)
            )

            self.assertEqual(result.returncode, 1, result.stderr)
            errors = " ".join(json.loads(result.stdout)["errors"])
            for field in (
                "event",
                "item_id",
                "state",
                "outcome",
                "evidence",
                "findings",
                "next",
            ):
                self.assertIn(field, errors)

    def test_milestone_lint_checks_progress_and_subject_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid = write_packet(
                root,
                {
                    "event": "milestone",
                    "item_id": "slice-a",
                    "state": "terminal",
                    "outcome": "validated",
                    "evidence": "pytest pass",
                    "findings": [],
                    "next": "continue",
                },
            )
            result = run_cli(
                "milestone", "lint", "--role", "writer", "--input", str(invalid)
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("subject_sha", result.stdout)

            progress = root / "progress.json"
            progress.write_text(
                json.dumps(
                    {
                        "event": "milestone",
                        "item_id": "slice-a",
                        "state": "progress",
                        "outcome": "working",
                        "evidence": "budget checkpoint: investigating parser",
                        "findings": [],
                        "next": "continue",
                    }
                ),
                encoding="utf-8",
            )
            accepted = run_cli(
                "milestone", "lint", "--role", "writer", "--input", str(progress)
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_collect_help_exposes_authorization_not_review_claim(self) -> None:
        result = run_cli("collect", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--authorized-sha", result.stdout)
        self.assertIn("--review-kind", result.stdout)
        self.assertNotIn("--reviewed-sha", result.stdout)


if __name__ == "__main__":
    unittest.main()
