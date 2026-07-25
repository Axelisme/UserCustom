from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "home" / ".codex" / "skills" / "orchestrate"


def load_admission_module():
    sys.path.insert(0, str(SKILL / "scripts"))
    try:
        return importlib.import_module("_orchestrate.admission")
    finally:
        sys.path.pop(0)


class OrchestrateV124AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.admission = load_admission_module()

    def args(self, root: Path, **overrides: object) -> argparse.Namespace:
        values: dict[str, object] = {
            "root": str(root),
            "base": "base",
            "tip": "tip",
            "max_slice_waves": 2,
            "max_slice_added": 1500,
            "max_file_added": 2000,
            "focus_days": 3,
            "slice_family_tokens": 1,
            "production_path": ["src"],
            "reachability_cmd": "true",
            "file_reachability_cmd": None,
            "burndown": None,
            "burndown_previous": None,
            "findings": 1,
            "backlog": 1,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def run_projection(
        self,
        root: Path,
        *,
        rows: list[tuple[int, int, str]] | None = None,
        commits: list[dict[str, object]] | None = None,
        **overrides: object,
    ) -> dict[str, object]:
        module = self.admission
        with (
            mock.patch.object(module, "exact_commit", side_effect=["base-sha", "tip-sha"]),
            mock.patch.object(module, "_numstat", return_value=rows or []),
            mock.patch.object(module, "_commits", return_value=commits or []),
            mock.patch.object(module, "_commit_added", return_value=0),
        ):
            return module.command_admission(self.args(root, **overrides))

    @staticmethod
    def checks(payload: dict[str, object]) -> dict[str, dict[str, object]]:
        return {entry["id"]: entry for entry in payload["checks"]}  # type: ignore[index]

    def test_loop_counts_collect_commits_not_distinct_slice_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            commits = [
                {
                    "sha": f"sha-{index}",
                    "date": datetime.now(UTC).isoformat(),
                    "subject": "Collect Wave k2",
                    "slice": "k2-same-slice",
                    "merge": True,
                }
                for index in range(3)
            ]
            checks = self.checks(
                self.run_projection(Path(temporary), commits=commits)
            )
        self.assertEqual(checks["slice_loop"]["status"], "refuse")
        self.assertEqual(checks["slice_loop"]["value"], 3)

    def test_burndown_without_previous_digest_is_undetermined(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "burndown.md"
            path.write_text("| slice | done |\n", encoding="utf-8")
            checks = self.checks(
                self.run_projection(Path(temporary), burndown=str(path))
            )
        self.assertEqual(checks["burndown"]["status"], "undetermined")

    def test_deletion_only_counts_declared_production_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checks = self.checks(
                self.run_projection(
                    Path(temporary),
                    rows=[(0, 20, "docs/old.md"), (10, 0, "src/new.py")],
                )
            )
        self.assertEqual(checks["deletion"]["status"], "refuse")
        self.assertEqual(checks["deletion"]["value"], 0)

    def test_large_reachable_file_does_not_refuse_mass(self) -> None:
        rows = [(2500, 0, "src/reachable.py")]
        with tempfile.TemporaryDirectory() as temporary:
            reachable = self.checks(
                self.run_projection(
                    Path(temporary), rows=rows, file_reachability_cmd="true"
                )
            )
            unreachable = self.checks(
                self.run_projection(
                    Path(temporary), rows=rows, file_reachability_cmd="false"
                )
            )
        self.assertEqual(reachable["file_mass"]["status"], "pass")
        self.assertEqual(unreachable["file_mass"]["status"], "refuse")

    def test_global_reachability_cannot_decide_an_oversized_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            checks = self.checks(
                self.run_projection(
                    Path(temporary),
                    rows=[(2500, 0, "src/unknown.py")],
                    reachability_cmd="true",
                )
            )
        self.assertEqual(checks["reachability"]["status"], "pass")
        self.assertEqual(checks["file_mass"]["status"], "undetermined")

    def test_focus_uses_only_slice_attributed_commits_without_hidden_floor(self) -> None:
        now = datetime.now(UTC).isoformat()
        one_slice = [
            {"sha": "a", "date": now, "subject": "work", "slice": "k2-a", "merge": False},
            {"sha": "b", "date": now, "subject": "misc", "slice": None, "merge": False},
        ]
        two_slices = [
            *one_slice,
            {"sha": "c", "date": now, "subject": "work", "slice": "m3-a", "merge": False},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            focused = self.checks(
                self.run_projection(Path(temporary), commits=one_slice)
            )
            distributed = self.checks(
                self.run_projection(Path(temporary), commits=two_slices)
            )
        self.assertEqual(focused["focus"]["status"], "refuse")
        self.assertEqual(distributed["focus"]["status"], "pass")

    def test_findings_and_backlog_counts_are_validated(self) -> None:
        invalid = (
            {"findings": -1},
            {"findings": 1, "backlog": -1},
            {"findings": 1, "backlog": 2},
            {"findings": None, "backlog": 1},
        )
        with tempfile.TemporaryDirectory() as temporary:
            for overrides in invalid:
                with self.subTest(overrides=overrides):
                    with self.assertRaises(self.admission.OrchestrateError):
                        self.admission.command_admission(
                            self.args(Path(temporary), **overrides)
                        )


if __name__ == "__main__":
    unittest.main()
