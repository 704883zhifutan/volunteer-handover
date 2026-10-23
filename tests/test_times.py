import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volunteer_handover.core.times import (  # noqa: E402
    dual_time_state,
    duration_minutes,
    gap_minutes,
    overlaps,
    parse_ts,
    version_active,
)


class DualTimeTest(unittest.TestCase):
    def test_missing_side_is_named(self):
        self.assertEqual(dual_time_state("", "2026-01-01T00:00:00"), "缺失(业务发生时间)")
        self.assertEqual(dual_time_state("2026-01-01T00:00:00", ""), "缺失(系统接收时间)")

    def test_inversion_flagged_regardless_of_threshold(self):
        self.assertEqual(dual_time_state("2026-01-01T10:00:00", "2026-01-01T09:59:00"), "时间倒挂")

    def test_small_lateness_is_not_noise_without_threshold(self):
        """阈值未核实时，普通来源晚 2 分钟不报警——否则误报会淹掉清单。"""
        self.assertEqual(dual_time_state("2026-01-01T10:00:00", "2026-01-01T10:02:00", None, "业务台账"), "正常")

    def test_batch_source_marked_without_threshold(self):
        self.assertEqual(dual_time_state("2026-01-01T10:00:00", "2026-01-01T12:00:00", None, "文件库"), "疑似回填")

    def test_threshold_applies_when_provided(self):
        self.assertEqual(dual_time_state("2026-01-01T10:00:00", "2026-01-01T10:30:00", 15, "业务台账"), "疑似回填")
        self.assertEqual(dual_time_state("2026-01-01T10:00:00", "2026-01-01T10:05:00", 15, "业务台账"), "正常")


class WindowTest(unittest.TestCase):
    def test_parse_formats(self):
        self.assertEqual(parse_ts("2026-10-03T07:00:00"), datetime(2026, 10, 3, 7))
        self.assertEqual(parse_ts("2026-10-03 07:00"), datetime(2026, 10, 3, 7))
        self.assertIsNone(parse_ts(""))

    def test_overlaps(self):
        a = (parse_ts("2026-10-03T09:00:00"), parse_ts("2026-10-03T13:00:00"))
        b = (parse_ts("2026-10-03T10:00:00"), parse_ts("2026-10-03T14:00:00"))
        c = (parse_ts("2026-10-03T13:00:00"), parse_ts("2026-10-03T15:00:00"))
        self.assertTrue(overlaps(*a, *b))
        self.assertFalse(overlaps(*a, *c))  # 首尾相接不算重叠

    def test_duration_and_gap(self):
        start = parse_ts("2026-10-03T07:00:00")
        end = parse_ts("2026-10-03T11:00:00")
        self.assertEqual(duration_minutes(start, end), 240)
        self.assertEqual(gap_minutes(start, parse_ts("2026-10-03T07:02:00")), 2.0)

    def test_version_active(self):
        row = {"version_valid_from": "2026-10-02T18:00:00", "version_valid_to": "2026-10-04T23:59:00"}
        self.assertTrue(version_active(row, parse_ts("2026-10-03T16:00:00")))
        self.assertFalse(version_active(row, parse_ts("2026-10-05T00:00:00")))
        self.assertFalse(version_active({"version_valid_from": "", "version_valid_to": ""}, None))


if __name__ == "__main__":
    unittest.main()
