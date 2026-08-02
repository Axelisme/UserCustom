"""Lane consumption: the count a recut must not be able to reset."""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "home/.codex/skills/orchestrate/scripts")
)

from _orchestrate import telemetry  # noqa: E402


def _task(*lanes: tuple[str, str | None]) -> types.SimpleNamespace:
    """A task whose telemetry records `lanes` as (lane_id, group) pairs."""
    path = Path(tempfile.mkdtemp()) / "telemetry.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(
                {
                    "event_version": 1,
                    "at": "2026-08-02T00:00:00+00:00",
                    "task_id": "t",
                    "operation": "lane-create",
                    "outcome": "success",
                    "lane_id": lane_id,
                    **({"group": group} if group is not None else {}),
                }
            )
            for lane_id, group in lanes
        )
    )
    return types.SimpleNamespace(telemetry_path=path)


class LaneConsumptionTests(unittest.TestCase):
    def test_a_recut_need_keeps_one_count_across_unrelated_lane_ids(self) -> None:
        # The field sequence: one need, ten lanes, and lane ids that stop
        # resembling each other by the third recut.
        task = _task(
            ("b51b-host-root", "b51b"),
            ("host-root-02", "b51b"),
            ("r3", "b51b"),
            ("r3-readmit", "b51b"),
            ("r4-token-replacement", "b51b"),
            ("r5-reset-baseline", "b51b"),
        )
        consumption = telemetry.lane_consumption(task)
        self.assertEqual(consumption["groups"]["b51b"]["count"], 6)
        self.assertEqual(consumption["at_threshold"], ["b51b"])

    def test_a_healthy_reslice_counts_as_separate_needs(self) -> None:
        # Cutting one need into three deliverable Slices is not consumption.
        task = _task(("c20a1", "c20a1"), ("c20a2", "c20a2"), ("c20b", "c20b"))
        consumption = telemetry.lane_consumption(task)
        self.assertEqual(
            {name: group["count"] for name, group in consumption["groups"].items()},
            {"c20a1": 1, "c20a2": 1, "c20b": 1},
        )
        self.assertNotIn("at_threshold", consumption)

    def test_the_count_names_its_members_so_a_wrong_grouping_is_visible(self) -> None:
        task = _task(("one", "shared"), ("two", "shared"))
        self.assertEqual(
            telemetry.lane_consumption(task)["groups"]["shared"]["lanes"], ["one", "two"]
        )

    def test_a_lane_recorded_before_the_group_existed_stands_alone(self) -> None:
        # Pre-v144 telemetry has no group. Standing alone under-counts; guessing
        # a group from the lane id over-counts, and a confident wrong count is
        # worse than a low one.
        task = _task(("legacy-a", None), ("legacy-b", None))
        consumption = telemetry.lane_consumption(task)
        self.assertEqual(sorted(consumption["groups"]), ["legacy-a", "legacy-b"])

    def test_the_warning_fires_only_at_the_threshold_and_names_the_lanes(self) -> None:
        below = _task(*((f"lane-{i}", "need") for i in range(5)))
        self.assertEqual(telemetry.lane_consumption_warnings(below, "need"), ())

        at = _task(*((f"lane-{i}", "need") for i in range(6)))
        (warning,) = telemetry.lane_consumption_warnings(at, "need")
        self.assertIn("6 lanes", warning)
        self.assertIn("lane-0", warning)
        self.assertIn("rebind", warning.lower())

    def test_an_absent_telemetry_file_reports_nothing_rather_than_failing(self) -> None:
        missing = types.SimpleNamespace(telemetry_path=Path(tempfile.mkdtemp()) / "absent")
        self.assertEqual(telemetry.lane_consumption(missing), {})


if __name__ == "__main__":
    unittest.main()
