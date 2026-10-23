"""指标：没有分母就不给百分比，没复核的不算误报。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from volunteer_handover.core.items import Finding  # noqa: E402
from volunteer_handover.core.metrics import compute, render_markdown, render_text  # noqa: E402


def _f(kind: str, status: str = "未复核", at: str = "", detail: str = "事实") -> Finding:
    return Finding("C1", kind, "S001", detail, "shifts.csv#L2", review_status=status, review_at=at)


class ComputeTest(unittest.TestCase):
    def test_no_review_gives_none_not_zero(self):
        m = compute([_f("缺岗未登记"), _f("缺岗未登记", detail="另一条")], "2026-10-03T17:00:00")
        self.assertIsNone(m.false_positive_rate)
        self.assertEqual(m.confirmed_rate, 0.0)
        self.assertEqual(m.unreviewed, 2)

    def test_rates_use_reviewed_as_denominator(self):
        findings = [
            _f("缺岗未登记", "已确认", "2026-10-03T17:10:00"),
            _f("缺岗未登记", "已确认", "2026-10-03T17:10:00", detail="b"),
            _f("时间倒挂", "已驳回", "2026-10-03T17:10:00"),
            _f("疑似回填"),
        ]
        m = compute(findings, "2026-10-03T17:00:00")
        self.assertAlmostEqual(m.false_positive_rate, 1 / 3)
        self.assertAlmostEqual(m.confirmed_rate, 2 / 4)
        self.assertEqual(m.unreviewed, 1)
        self.assertEqual(m.queued, 0)

    def test_queued_counts_as_reviewed(self):
        m = compute([_f("缺岗未登记", "转人工队列", "2026-10-03T17:10:00")], "2026-10-03T17:00:00")
        self.assertEqual(m.reviewed, 1)
        self.assertEqual(m.rejected, 0)
        self.assertEqual(m.false_positive_rate, 0.0)

    def test_lag_is_measured_from_run_time(self):
        m = compute([_f("缺岗未登记", "已确认", "2026-10-03T19:00:00")], "2026-10-03T17:00:00")
        mean, longest = m.lag_summary()
        self.assertAlmostEqual(mean, 2.0)
        self.assertAlmostEqual(longest, 2.0)

    def test_review_earlier_than_run_is_flagged_not_averaged(self):
        m = compute([_f("缺岗未登记", "已确认", "2026-10-01T09:00:00")], "2026-10-03T17:00:00")
        self.assertEqual(m.lag_hours, [])
        self.assertEqual(len(m.lag_anomalies), 1)
        mean, _ = m.lag_summary()
        self.assertIsNone(mean)

    def test_noisy_types_sorted_by_rejected_rate(self):
        findings = [
            _f("A 类", "已驳回", "2026-10-03T17:10:00"),
            _f("A 类", "已驳回", "2026-10-03T17:10:00", detail="a2"),
            _f("B 类", "已驳回", "2026-10-03T17:10:00"),
            _f("B 类", "已确认", "2026-10-03T17:10:00", detail="b2"),
            _f("B 类", "已确认", "2026-10-03T17:10:00", detail="b3"),
        ]
        m = compute(findings, "2026-10-03T17:00:00")
        self.assertEqual([t.type for t in m.noisy_types], ["A 类", "B 类"])


class RenderTest(unittest.TestCase):
    def test_text_says_sample_insufficient(self):
        m = compute([_f("缺岗未登记")], "2026-10-03T17:00:00")
        text = render_text(m)
        self.assertIn("样本不足，暂不计算", text)
        self.assertIn("未复核", text)

    def test_markdown_carries_the_metric_definitions(self):
        m = compute([_f("缺岗未登记", "已驳回", "2026-10-03T17:30:00")], "2026-10-03T17:00:00")
        md = render_markdown(m, "B-1")
        self.assertIn("误报率 = 已驳回 / 已复核", md)
        self.assertIn("试点要求 100%", md)
        self.assertIn("不是工时", md)
        self.assertIn("下一步该收窄哪一类", md)

    def test_markdown_warns_when_unreviewed_remains(self):
        m = compute([_f("缺岗未登记"), _f("缺岗未登记", detail="b")], "2026-10-03T17:00:00")
        self.assertIn("不能当整体结论", render_markdown(m, "B-1"))


if __name__ == "__main__":
    unittest.main()
