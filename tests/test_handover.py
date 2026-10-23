import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volunteer_handover.core.handover import (  # noqa: E402
    build_checklist,
    checklist_findings,
    parse_open_items,
)
from volunteer_handover.core.times import parse_ts  # noqa: E402
from volunteer_handover.utils.csvio import Row  # noqa: E402

AS_OF = parse_ts("2026-10-03T16:00:00")


def H(line, **overrides):
    data = {
        "handover_id": "H001",
        "shift_id": "S001",
        "from_person": "Z1",
        "to_person": "Z2",
        "handover_at": "2026-10-03T11:00:00",
        "accepted_at": "2026-10-03T11:02:00",
        "version_no": "v3",
        "open_items": "OI-1;清点物资;2026-10-03T20:00:00;Z2;未结",  # 晚于 as_of，不算逾期
        "notes": "",
    }
    data.update(overrides)
    return Row(data=data, locator=f"handover.csv#L{line}", file_name="handover.csv", line_no=line)


def S(line, **overrides):
    data = {
        "shift_id": "S001",
        "position_id": "P01",
        "person_code": "Z1",
        "confirm_status": "confirmed",
        "version_no": "v3",
        "version_valid_from": "2026-10-02T18:00:00",
        "version_valid_to": "2026-10-04T23:59:00",
        "superseded_by": "",
        "void_reason": "",
    }
    data.update(overrides)
    return Row(data=data, locator=f"shifts.csv#L{line}", file_name="shifts.csv", line_no=line)


class ParseOpenItemsTest(unittest.TestCase):
    def test_two_items(self):
        items = parse_open_items("OI-1;甲;2026-10-03T12:00:00;Z2;未结|OI-2;乙;;Z3;已结")
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0].is_open)
        self.assertFalse(items[1].is_open)
        self.assertIsNone(items[1].deadline)

    def test_broken_shape_kept_not_dropped(self):
        items = parse_open_items("OI-9 缺字段")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, "格式无法判定")


class BuildChecklistTest(unittest.TestCase):
    def test_clean_handover_has_no_flags(self):
        checks = build_checklist([H(2)], {"S001": S(2)}, AS_OF)
        self.assertEqual(checks[0].flags, [])
        self.assertEqual(checks[0].version_state, "有效")

    def test_no_signoff(self):
        checks = build_checklist([H(2, accepted_at="")], {"S001": S(2)}, AS_OF)
        self.assertIn("未签收", checks[0].flags)

    def test_same_person(self):
        checks = build_checklist([H(2, to_person="Z1")], {"S001": S(2)}, AS_OF)
        self.assertIn("交出人与接收人为同一人", checks[0].flags)

    def test_open_item_without_owner(self):
        checks = build_checklist([H(2, open_items="OI-1;甲;2026-10-03T12:00:00;;未结")], {"S001": S(2)}, AS_OF)
        self.assertIn("OI-1 未结项无责任人", checks[0].flags)

    def test_overdue_item(self):
        checks = build_checklist([H(2, open_items="OI-1;甲;2026-10-03T09:00:00;Z2;未结")], {"S001": S(2)}, AS_OF)
        self.assertIn("OI-1 逾期未结", checks[0].flags)

    def test_closed_item_not_overdue(self):
        checks = build_checklist([H(2, open_items="OI-1;甲;2026-10-03T09:00:00;Z2;已结")], {"S001": S(2)}, AS_OF)
        self.assertEqual(checks[0].flags, [])

    def test_version_mismatch_between_handover_and_shift(self):
        checks = build_checklist([H(2, version_no="v2")], {"S001": S(2)}, AS_OF)
        self.assertTrue(any("≠排班版本" in f for f in checks[0].flags))

    def test_missing_shift_row_is_broken_chain(self):
        checks = build_checklist([H(2)], {}, AS_OF)
        self.assertIn("版本找不到对应班次（断链）", checks[0].flags)

    def test_no_is_complete_judgement(self):
        """“完成”的定义未确认（G3），代码不得代为判定。"""
        checks = build_checklist([H(2)], {"S001": S(2)}, AS_OF)
        self.assertFalse(hasattr(checks[0], "is_complete"))


class DuplicateItemIdTest(unittest.TestCase):
    def test_same_item_id_twice_is_flagged(self):
        """OI-1 出现两次时，"谁负责、结没结"会变成两说：保留原样，但必须标出来。"""
        checks = build_checklist(
            [H(2, open_items="OI-1;甲;2026-10-03T20:00:00;Z2;未结|OI-1;乙;2026-10-03T20:00:00;Z3;未结")],
            {"S001": S(2)},
            AS_OF,
        )
        self.assertTrue(any("编号重复" in f for f in checks[0].flags), checks[0].flags)

    def test_duplicate_id_becomes_its_own_type(self):
        checks = build_checklist(
            [H(2, open_items="OI-1;甲;2026-10-03T20:00:00;Z2;未结|OI-1;乙;2026-10-03T20:00:00;Z3;未结")],
            {"S001": S(2)},
            AS_OF,
        )
        types = {f.type for f in checklist_findings(checks)}
        self.assertEqual(types, {"未结项编号重复"})

    def test_distinct_item_ids_are_quiet(self):
        checks = build_checklist(
            [H(2, open_items="OI-1;甲;2026-10-03T20:00:00;Z2;未结|OI-2;乙;2026-10-03T20:00:00;Z3;未结")],
            {"S001": S(2)},
            AS_OF,
        )
        self.assertEqual(checks[0].flags, [])


class FindingsTest(unittest.TestCase):
    def test_flags_become_traceable_findings(self):
        checks = build_checklist([H(2, accepted_at="")], {"S001": S(2)}, AS_OF)
        findings = checklist_findings(checks)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "C5")
        self.assertEqual(findings[0].source_locator, "handover.csv#L2")
        self.assertTrue(findings[0].suggestion.startswith("仅提示"))


if __name__ == "__main__":
    unittest.main()
