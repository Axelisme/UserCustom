from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"
SCRIPT = SKILL / "scripts" / "orchestrate.py"


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


def dispatch_packet(
    *,
    basis_sha: str,
    sections: tuple[str, ...] | None = None,
    hard_critical_axes: str = "security",
) -> str:
    required = sections or (
        "Authority",
        "Acceptance",
        "Non-goals",
        "Exact literals",
        "Oracles",
        "Review policy",
        "Stop conditions",
    )
    body = "\n\n".join(f"## {heading}\n\n{heading} content" for heading in required)
    return f"""---
dispatch_packet_version: 1
packet_id: critical-slice-a
role: writer
basis_sha: {basis_sha}
hard_critical_axes: {hard_critical_axes}
---

# Critical slice A

{body}
"""


def copy_release_home(root: Path) -> Path:
    home = root / "home"
    skill = home / ".codex" / "skills" / "orchestrate"
    shutil.copytree(SKILL, skill)
    for runtime, suffix in ((".codex", ".toml"), (".claude", ".md")):
        agents = home / runtime / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        source = ROOT / "home" / runtime / "agents"
        for role in ("contract-planner", "implementer", "reviewer"):
            shutil.copy2(source / f"{role}{suffix}", agents / f"{role}{suffix}")
    return skill


class DispatchPacketCliTests(unittest.TestCase):
    def test_atomic_cutover_is_critical_but_public_wire_alone_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            source = root / "dispatch.md"
            source.write_text(
                dispatch_packet(basis_sha=basis, hard_critical_axes="atomic-cutover"),
                encoding="utf-8",
            )
            accepted = run_cli(
                "packet",
                "publish",
                "--root",
                str(root),
                "--task-id",
                "demo",
                "--input",
                str(source),
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

            source.write_text(
                dispatch_packet(basis_sha=basis, hard_critical_axes="public-wire"),
                encoding="utf-8",
            )
            rejected = run_cli(
                "packet",
                "publish",
                "--root",
                str(root),
                "--task-id",
                "demo",
                "--input",
                str(source),
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("hard_critical_axes", rejected.stderr)

    def test_publish_is_content_addressed_and_inspect_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            source = root / "dispatch.md"
            source.write_text(dispatch_packet(basis_sha=basis), encoding="utf-8")

            published = run_cli(
                "packet",
                "publish",
                "--root",
                str(root),
                "--task-id",
                "demo",
                "--input",
                str(source),
            )

            self.assertEqual(published.returncode, 0, published.stderr)
            payload = json.loads(published.stdout)
            self.assertTrue(payload["created"])
            self.assertFalse(payload["authority_inferred"])
            self.assertFalse(payload["dispatch_inferred"])
            self.assertEqual(payload["release_preflight"]["skill_version"], 61)
            packet_path = Path(payload["path"])
            self.assertTrue(packet_path.is_file())
            self.assertEqual(packet_path.name, f"{payload['sha256']}.md")

            inspected = run_cli(
                "packet",
                "inspect",
                "--root",
                str(root),
                "--task-id",
                "demo",
                "--sha256",
                payload["sha256"],
            )
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(json.loads(inspected.stdout)["sha256"], payload["sha256"])

            again = run_cli(
                "packet",
                "publish",
                "--root",
                str(root),
                "--task-id",
                "demo",
                "--input",
                str(source),
            )
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertFalse(json.loads(again.stdout)["created"])

    def test_invalid_packet_fails_before_creating_agent_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            basis = initialize_repo(root)
            source = root / "dispatch.md"
            source.write_text(
                dispatch_packet(basis_sha=basis, sections=("Authority", "Acceptance")),
                encoding="utf-8",
            )

            result = run_cli(
                "packet",
                "publish",
                "--root",
                str(root),
                "--task-id",
                "demo",
                "--input",
                str(source),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("required section", result.stderr)
            self.assertFalse((root / ".agent_state").exists())

    def test_mutation_preflight_fails_closed_but_inspection_remains_available(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            copied_skill = copy_release_home(temporary_root / "release")
            runtime = copied_skill / "runtime-codex.md"
            runtime.write_text(
                runtime.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8"
            )
            repo = temporary_root / "repo"
            repo.mkdir()
            basis = initialize_repo(repo)
            source = repo / "dispatch.md"
            source.write_text(dispatch_packet(basis_sha=basis), encoding="utf-8")

            inspect = run_cli(
                "--skill-dir",
                str(copied_skill),
                "queue",
                "inspect",
                "--root",
                str(repo),
                "--task-id",
                "demo",
                "--role",
                "writer",
                "--lease-id",
                "writer1",
                "--generation",
                "1",
            )
            self.assertEqual(inspect.returncode, 0, inspect.stderr)
            self.assertFalse((repo / ".agent_state").exists())

            publish = run_cli(
                "--skill-dir",
                str(copied_skill),
                "packet",
                "publish",
                "--root",
                str(repo),
                "--task-id",
                "demo",
                "--input",
                str(source),
            )
            self.assertEqual(publish.returncode, 2)
            self.assertIn("release preflight failed", publish.stderr)
            self.assertFalse((repo / ".agent_state").exists())


if __name__ == "__main__":
    unittest.main()
