"""复核回填：没人负责的结论不生效，对不上的编号不能被悄悄丢掉。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from volunteer_handover.core.engine import run  # noqa: E402
from volunteer_handover.core.items import Finding, make_finding_id  # noqa: E402
from volunteer_handover.core.review import apply_reviews, load_reviews  # noqa: E402


def _write(tmp: str, body: str) -> str:
    path = Path(tmp) / "review.csv"
    path.write_text("编号,复核状态,复核人,复核时间,备注\n" + body, encoding="utf-8")
    return str(path)


def _finding(fid: str = "F-aaa", detail: str = "事实") -> Finding:
    return Finding("C1", "缺岗未登记", "S001", detail, "shifts.csv#L2", fid=fid)


class LoadReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vh-review-")

    def test_missing_file_is_not_an_error(self):
        entries, problems = load_reviews(str(Path(self.tmp) / "nope.csv"))
        self.assertEqual(entries, [])
        self.assertEqual(problems, [])

    def test_valid_entry_is_loaded(self):
        path = _write(self.tmp, "F-aaa,已确认,唐映秋,2026-10-03T17:20:00,核实过了\n")
        entries, problems = load_reviews(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(problems, [])
        self.assertEqual(entries[0].by, "唐映秋")

    def test_invalid_status_is_rejected(self):
        path = _write(self.tmp, "F-aaa,通过,唐映秋,2026-10-03T17:20:00,\n")
        entries, problems = load_reviews(path)
        self.assertEqual(entries, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("工具不替人做结论", problems[0].reason)

    def test_missing_reviewer_is_rejected(self):
        path = _write(self.tmp, "F-aaa,已确认,,2026-10-03T17:20:00,\n")
        entries, problems = load_reviews(path)
        self.assertEqual(entries, [])
        self.assertIn("缺复核人", problems[0].reason)

    def test_missing_time_is_rejected(self):
        path = _write(self.tmp, "F-aaa,已确认,唐映秋,,\n")
        entries, problems = load_reviews(path)
        self.assertEqual(entries, [])
        self.assertIn("缺复核时间", problems[0].reason)

    def test_missing_id_is_rejected(self):
        path = _write(self.tmp, ",已确认,唐映秋,2026-10-03T17:20:00,\n")
        entries, problems = load_reviews(path)
        self.assertEqual(entries, [])
        self.assertIn("缺编号", problems[0].reason)


class ApplyReviewTest(unittest.TestCase):
    def test_apply_sets_status_and_reviewer(self):
        target = _finding("F-aaa")
        entries, _ = load_reviews(_write(tempfile.mkdtemp(), "F-aaa,已确认,唐映秋,2026-10-03T17:20:00,\n"))
        result = apply_reviews([target], entries)
        self.assertEqual(result.applied, 1)
        self.assertEqual(target.review_status, "已确认")
        self.assertEqual(target.review_by, "唐映秋")
        self.assertEqual(result.reviewed, 1)

    def test_unmatched_id_is_reported_not_dropped(self):
        entries, _ = load_reviews(_write(tempfile.mkdtemp(), "F-old,已确认,唐映秋,2026-10-03T17:20:00,\n"))
        result = apply_reviews([_finding("F-new")], entries)
        self.assertEqual(result.applied, 0)
        self.assertEqual(len(result.unmatched), 1)
        self.assertEqual(result.unmatched[0].fid, "F-old")

    def test_duplicate_id_keeps_first_and_reports(self):
        tmp = tempfile.mkdtemp()
        path = _write(
            tmp,
            "F-aaa,已确认,唐映秋,2026-10-03T17:20:00,第一次\n"
            "F-aaa,已驳回,林亦舟,2026-10-03T17:30:00,第二次\n",
        )
        entries, _ = load_reviews(path)
        target = _finding("F-aaa")
        result = apply_reviews([target], entries)
        self.assertEqual(result.applied, 1)
        self.assertEqual(target.review_status, "已确认")
        self.assertTrue(any("编号重复" in p.reason for p in result.problems))
        self.assertEqual(str(Path(tmp)), str(Path(tmp)))


class FindingIdTest(unittest.TestCase):
    def test_same_content_same_id(self):
        a = make_finding_id("C1", "缺岗未登记", "S001", "shifts.csv#L2", "t1", "t2", "事实")
        b = make_finding_id("C1", "缺岗未登记", "S001", "shifts.csv#L2", "t1", "t2", "事实")
        self.assertEqual(a, b)

    def test_detail_changes_id(self):
        a = make_finding_id("C5", "未确认项超时", "H001/S002", "handover.csv#L2", "", "", "OI-1 逾期未结")
        b = make_finding_id("C5", "未确认项超时", "H001/S002", "handover.csv#L2", "", "", "OI-2 逾期未结")
        self.assertNotEqual(a, b)

    def test_ids_are_unique_across_a_real_run(self):
        result = run(str(ROOT / "data"), {})
        ids = [f.fid for f in result.items.findings]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(fid.startswith("F-") for fid in ids))


class EngineReviewTest(unittest.TestCase):
    def test_run_attaches_review_and_metrics(self):
        tmp = tempfile.mkdtemp()
        first = run(str(ROOT / "data"), {})
        fid = first.items.findings[0].fid
        path = _write(tmp, f"{fid},已确认,唐映秋,2026-10-03T17:20:00,\n")
        result = run(str(ROOT / "data"), {}, review_path=path, run_at="2026-10-03T17:00:00")
        self.assertIsNotNone(result.review)
        self.assertEqual(result.review.applied, 1)
        self.assertIsNotNone(result.metrics)
        self.assertEqual(result.metrics.confirmed, 1)
        self.assertIn("已回填 1/", result.items.review_note)

    def test_unmatched_review_produces_warning(self):
        tmp = tempfile.mkdtemp()
        path = _write(tmp, "F-missing,已确认,唐映秋,2026-10-03T17:20:00,\n")
        result = run(str(ROOT / "data"), {}, review_path=path, run_at="2026-10-03T17:00:00")
        self.assertTrue(any("对不上" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
