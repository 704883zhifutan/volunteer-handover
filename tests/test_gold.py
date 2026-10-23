"""金标比对：召回要有分母；没标注的不能算成误报。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from volunteer_handover.core.gold import (  # noqa: E402
    extract_pairs,
    load_gold,
    parse_gold,
    render_markdown,
    score,
)
from volunteer_handover.core.items import Finding  # noqa: E402
from volunteer_handover.utils.csvio import read_rows  # noqa: E402


def _gold(tmp: str, body: str) -> str:
    path = Path(tmp) / "gold.csv"
    path.write_text("shift_a,shift_b,是否真重叠,标注人\n" + body, encoding="utf-8")
    return str(path)


def _overlap(a: str, b: str) -> Finding:
    return Finding(
        "C2", "疑似重复占位", "Z0007", f"{a} 与 {b} 重叠", "shifts.csv#L5",
        refs=f"{a},{b}",
    )


class ParseGoldTest(unittest.TestCase):
    def test_parses_true_and_false(self):
        pairs, problems = parse_gold(read_rows(_gold(tempfile.mkdtemp(), "S1,S2,是,傅景\nS1,S3,否,傅景\n")))
        self.assertEqual([p.overlaps for p in pairs], [True, False])
        self.assertEqual(problems, [])

    def test_unknown_truth_is_a_problem(self):
        pairs, problems = parse_gold(read_rows(_gold(tempfile.mkdtemp(), "S1,S2,大概吧,傅景\n")))
        self.assertEqual(pairs, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("只认 是/否", problems[0].reason)

    def test_self_pair_is_rejected(self):
        pairs, problems = parse_gold(read_rows(_gold(tempfile.mkdtemp(), "S1,S1,是,傅景\n")))
        self.assertEqual(pairs, [])
        self.assertIn("自己", problems[0].reason)

    def test_missing_file_says_g1_cannot_close(self):
        pairs, problems = load_gold(str(Path(tempfile.mkdtemp()) / "nope.csv"))
        self.assertEqual(pairs, [])
        self.assertIn("G1 无法关闭", problems[0].reason)

    def test_sample_gold_file_loads_cleanly(self):
        pairs, problems = load_gold(str(ROOT / "data" / "gold_overlap.csv"))
        self.assertEqual(problems, [])
        self.assertEqual(sum(1 for p in pairs if p.overlaps), 1)


class ExtractPairsTest(unittest.TestCase):
    def test_pair_is_order_independent(self):
        pairs = extract_pairs([_overlap("S005", "S004")])
        self.assertIn(("S004", "S005"), pairs)

    def test_finding_without_refs_is_ignored(self):
        no_refs = Finding("C2", "疑似重复占位", "Z0007", "重叠", "shifts.csv#L5")
        self.assertEqual(extract_pairs([no_refs]), {})

    def test_only_c2_is_used_by_default(self):
        other = Finding("C1", "缺岗未登记", "S001", "事实", "shifts.csv#L2", refs="S001,S002")
        self.assertEqual(extract_pairs([other]), {})


class ScoreTest(unittest.TestCase):
    def test_perfect_recall_and_precision(self):
        gold, _ = parse_gold(read_rows(_gold(tempfile.mkdtemp(), "S1,S2,是,傅景\nS1,S3,否,傅景\n")))
        result = score(gold, [_overlap("S1", "S2")])
        self.assertEqual((result.tp, result.fn, result.fp), (1, 0, 0))
        self.assertEqual(result.recall, 1.0)
        self.assertEqual(result.precision, 1.0)
        self.assertTrue(result.g1_ready)

    def test_missed_overlap_breaks_recall(self):
        gold, _ = parse_gold(read_rows(_gold(tempfile.mkdtemp(), "S1,S2,是,傅景\nS3,S4,是,傅景\n")))
        result = score(gold, [_overlap("S1", "S2")])
        self.assertEqual(result.recall, 0.5)
        self.assertFalse(result.g1_ready)
        self.assertEqual([g.key for g in result.missed], [("S3", "S4")])

    def test_false_alarm_against_labeled_negative(self):
        gold, _ = parse_gold(read_rows(_gold(tempfile.mkdtemp(), "S1,S2,否,傅景\n")))
        result = score(gold, [_overlap("S1", "S2")])
        self.assertEqual(result.fp, 1)
        self.assertEqual(result.precision, 0.0)
        # 金标里没有一条真重叠 → 召回没有分母，只能是"无法计算"，不能写成 0%
        self.assertIsNone(result.recall)
        self.assertFalse(result.g1_ready)

    def test_unlabeled_is_not_a_false_alarm(self):
        gold, _ = parse_gold(read_rows(_gold(tempfile.mkdtemp(), "S1,S2,是,傅景\n")))
        result = score(gold, [_overlap("S1", "S2"), _overlap("S8", "S9")])
        self.assertEqual(result.fp, 0)
        self.assertEqual(result.unlabeled, [("S8", "S9")])
        self.assertFalse(result.g1_ready)

    def test_no_gold_true_means_no_recall(self):
        gold, _ = parse_gold(read_rows(_gold(tempfile.mkdtemp(), "S1,S2,否,傅景\n")))
        result = score(gold, [])
        self.assertIsNone(result.recall)
        self.assertFalse(result.g1_ready)

    def test_markdown_explains_why_g1_cannot_close(self):
        gold, problems = parse_gold(read_rows(_gold(tempfile.mkdtemp(), "S1,S2,是,傅景\nS3,S4,是,傅景\n")))
        result = score(gold, [_overlap("S1", "S2")])
        result.problems.extend(problems)
        md = render_markdown(result, "B-1", "data/gold_overlap.csv")
        self.assertIn("还不能关闭", md)
        self.assertIn("召回", md)
        self.assertIn("漏报", md)


if __name__ == "__main__":
    unittest.main()
