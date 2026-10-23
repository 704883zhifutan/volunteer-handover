import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volunteer_handover.core import diff  # noqa: E402
from volunteer_handover.core.items import Finding, ItemSheet  # noqa: E402


def F(code="C1", type="缺岗未登记", subject="S001", detail="排班有、签到无", locator="shifts.csv#L2", **kw):
    return Finding(code=code, type=type, subject=subject, detail=detail, source_locator=locator,
                   occurred_at="2026-10-03T07:00:00", **kw)


class ComputeTest(unittest.TestCase):
    def test_new_persist_gone(self):
        prev = [F(subject="S001"), F(subject="S002")]
        curr = [F(subject="S001"), F(subject="S003")]
        entries = diff.compute(prev, curr)
        kinds = {e.finding.subject: e.kind for e in entries}
        self.assertEqual(kinds, {"S001": diff.PERSIST, "S002": diff.GONE, "S003": diff.NEW})
        self.assertEqual(diff.counts(entries), {diff.NEW: 1, diff.PERSIST: 1, diff.GONE: 1})

    def test_same_business_key_and_same_fid_is_plain_persist(self):
        finding = F()
        entries = diff.compute([finding], [finding])
        self.assertEqual(entries[0].kind, diff.PERSIST)
        self.assertEqual(entries[0].note, "")

    def test_changed_detail_is_persist_with_note(self):
        """编号是内容指纹：细节变了编号就换，但业务身份没变，所以不是"消失又新增"。"""
        old = F(detail="排班有、签到无")
        new = F(detail="排班有、签到无（补充了点位）")
        self.assertNotEqual(old.fid, new.fid)
        entries = diff.compute([old], [new])
        self.assertEqual(entries[0].kind, diff.PERSIST)
        self.assertIn("内容有变", entries[0].note)

    def test_type_change_counts_as_gone_and_new(self):
        """同一对象换了类型（编号断链 → 计划外到岗）要看得见，不能被合并。"""
        entries = diff.compute([F(type="编号断链", detail="x")], [F(type="计划外到岗", detail="x")])
        self.assertEqual({e.kind for e in entries}, {diff.GONE, diff.NEW})

    def test_two_findings_in_one_group_do_not_collapse(self):
        """同一个交接的两条未结项逾期：业务身份相同，但必须是两条，不能被"一条对一条"吞掉。"""
        prev = [F(code="C5", type="未确认项超时", subject="H001/S002", detail="OI-1 逾期", locator="handover.csv#L2"),
                F(code="C5", type="未确认项超时", subject="H001/S002", detail="OI-2 逾期", locator="handover.csv#L2")]
        curr = list(prev)
        entries = diff.compute(prev, curr)
        self.assertEqual(diff.counts(entries), {diff.NEW: 0, diff.PERSIST: 2, diff.GONE: 0})

    def test_second_item_added_later_shows_as_new(self):
        base = F(code="C5", type="未确认项超时", subject="H001/S002", detail="OI-1 逾期", locator="handover.csv#L2")
        extra = F(code="C5", type="未确认项超时", subject="H001/S002", detail="OI-2 逾期", locator="handover.csv#L2")
        entries = diff.compute([base], [base, extra])
        self.assertEqual(diff.counts(entries), {diff.NEW: 1, diff.PERSIST: 1, diff.GONE: 0})

    def test_total_never_exceeds_inputs(self):
        prev = [F(subject="S1"), F(subject="S1"), F(subject="S2")]
        curr = [F(subject="S1"), F(subject="S3")]
        entries = diff.compute(prev, curr)
        # 配对的一条只出一次；没配上的按原样出。S1 出一条持续、一条消失，S2 消失，S3 新增
        self.assertEqual(diff.counts(entries), {diff.NEW: 1, diff.PERSIST: 1, diff.GONE: 2})

    def test_empty_on_both_sides(self):
        self.assertEqual(diff.compute([], []), [])

    def test_ordering_new_persist_gone(self):
        entries = diff.compute([F(subject="S8"), F(subject="S9")], [F(subject="S1"), F(subject="S9")])
        self.assertEqual(entries[0].kind, diff.NEW)
        self.assertEqual(entries[-1].kind, diff.GONE)


class RenderTest(unittest.TestCase):
    def test_markdown_carries_the_disappear_warning(self):
        entries = diff.compute([F()], [])
        text = diff.render_markdown(entries, "上一批", "本批")
        self.assertIn("消失不等于已解决", text)
        self.assertIn("上一批 → 本批", text)
        self.assertIn("| 缺岗未登记 |", text)

    def test_markdown_says_when_identical(self):
        text = diff.render_markdown([], "a", "b")
        self.assertIn("没有差异", text)

    def test_text_mentions_gone_caution(self):
        text = diff.render_text(diff.compute([F()], []))
        self.assertIn("消失 1", text)
        self.assertIn("不等于已解决", text)

    def test_pipe_in_detail_does_not_break_table(self):
        entries = diff.compute([], [F(detail="a|b")])
        self.assertNotIn("a|b", diff.render_markdown(entries, "x", "y"))


class RoundTripTest(unittest.TestCase):
    def test_load_items_reads_what_itemsheet_wrote(self):
        tmp = Path(tempfile.mkdtemp())
        sheet = ItemSheet(batch_id="B1", findings=[F(), F(subject="S002", type="疑似重复占位")])
        path = tmp / "items.csv"
        sheet.to_csv(path)
        loaded = diff.load_items(path)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].type, "缺岗未登记")
        self.assertEqual(loaded[0].fid, sheet.findings[0].fid)

    def test_csv_has_kind_column(self):
        tmp = Path(tempfile.mkdtemp())
        out = diff.to_csv(diff.compute([], [F()]), tmp / "diff.csv")
        head = out.read_text(encoding="utf-8-sig").splitlines()[0]
        self.assertTrue(head.startswith("变化,编号"))


if __name__ == "__main__":
    unittest.main()
