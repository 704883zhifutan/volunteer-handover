import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volunteer_handover.core import checks  # noqa: E402
from volunteer_handover.core.boundary import Boundary  # noqa: E402
from volunteer_handover.core.trace import Snapshot  # noqa: E402
from volunteer_handover.core.times import parse_ts  # noqa: E402
from volunteer_handover.utils.csvio import Row  # noqa: E402

BASE = {
    "shift_id": "S001",
    "batch_id": "B1",
    "position_id": "P01",
    "person_code": "Z1",
    "skill_tags": "SKILL-GUIDE",
    "window_start": "2026-10-03T07:00:00",
    "window_end": "2026-10-03T11:00:00",
    "window_minutes": "240",
    "confirm_status": "confirmed",
    "version_no": "v3",
    "version_valid_from": "2026-10-02T18:00:00",
    "version_valid_to": "2026-10-04T23:59:00",
    "superseded_by": "",
    "void_reason": "",
    "occurred_at": "2026-10-03T07:00:00",
    "received_at": "2026-10-03T06:40:00",
}


def R(file_name, line, **overrides):
    data = dict(BASE)
    data.update({k: v for k, v in overrides.items()})
    return Row(data=data, locator=f"{file_name}#L{line}", file_name=file_name, line_no=line)


def H(file_name, line, **overrides):
    data = {"handover_id": "H1", "shift_id": "S001", "from_person": "Z1", "to_person": "Z2",
            "handover_at": "2026-10-03T11:00:00", "accepted_at": "2026-10-03T11:05:00",
            "version_no": "v3", "open_items": ""}
    data.update(overrides)
    return Row(data=data, locator=f"{file_name}#L{line}", file_name=file_name, line_no=line)


def C(file_name, line, **overrides):
    data = {
        "checkin_id": "K1",
        "shift_id": "S001",
        "person_code": "Z1",
        "site_id": "S-A",
        "occurred_at": "2026-10-03T07:01:00",
        "received_at": "2026-10-03T07:02:00",
        "source_tool": "业务台账",
    }
    data.update(overrides)
    return Row(data=data, locator=f"{file_name}#L{line}", file_name=file_name, line_no=line)


POS = {"P01": Row(data={"position_id": "P01", "site_id": "S-A", "category": "通用"},
                  locator="positions.csv#L2", file_name="positions.csv", line_no=2)}


class C1Test(unittest.TestCase):
    def test_missing_checkin_is_flagged(self):
        found = checks.c1_cross_check([R("shifts.csv", 2)], [], POS, {"S001"})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].type, "缺岗未登记")
        self.assertEqual(found[0].code, "C1")

    def test_site_mismatch(self):
        found = checks.c1_cross_check([R("shifts.csv", 2)], [C("checkins.csv", 2, site_id="S-Z")], POS, {"S001"})
        self.assertEqual([f.type for f in found], ["排班表与现场不一致"])
        self.assertIn("checkins.csv#L2", found[0].source_locator)

    def test_person_mismatch(self):
        found = checks.c1_cross_check([R("shifts.csv", 2)], [C("checkins.csv", 2, person_code="Z9")], POS, {"S001"})
        self.assertEqual([f.type for f in found], ["排班表与现场不一致"])

    def test_out_of_scope_shift_silent(self):
        found = checks.c1_cross_check([R("shifts.csv", 2)], [], POS, set())
        self.assertEqual(found, [])


class C2Test(unittest.TestCase):
    def test_overlapping_two_sites_flagged(self):
        a = R("shifts.csv", 2, shift_id="S001", position_id="P05",
              window_start="2026-10-03T09:00:00", window_end="2026-10-03T13:00:00")
        b = R("shifts.csv", 3, shift_id="S002", position_id="P02",
              window_start="2026-10-03T10:00:00", window_end="2026-10-03T14:00:00")
        found = checks.c2_double_booking([a, b], {"S001", "S002"})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].type, "疑似重复占位")
        self.assertIn("shifts.csv#L2", found[0].source_locator)

    def test_same_position_back_to_back_allowed(self):
        a = R("shifts.csv", 2, shift_id="S001", window_start="2026-10-03T07:00:00", window_end="2026-10-03T11:00:00")
        b = R("shifts.csv", 3, shift_id="S002", window_start="2026-10-03T11:00:00", window_end="2026-10-03T15:00:00")
        self.assertEqual(checks.c2_double_booking([a, b], {"S001", "S002"}), [])


class C4Test(unittest.TestCase):
    def test_superseded_version_flagged(self):
        found = checks.c4_version([R("shifts.csv", 2, superseded_by="v4")], {"S001"},
                                  parse_ts("2026-10-03T16:00:00"))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].type, "版本断链或过期")

    def test_unconfirmed_flagged(self):
        found = checks.c4_version([R("shifts.csv", 2, confirm_status="unconfirmed")], {"S001"},
                                  parse_ts("2026-10-03T16:00:00"))
        self.assertEqual(found[0].type, "版本未确认")

    def test_expired_window_flagged(self):
        found = checks.c4_version([R("shifts.csv", 2)], {"S001"}, parse_ts("2026-10-09T00:00:00"))
        self.assertEqual(len(found), 1)

    def test_valid_version_silent(self):
        self.assertEqual(checks.c4_version([R("shifts.csv", 2)], {"S001"}, parse_ts("2026-10-03T16:00:00")), [])


class C6Test(unittest.TestCase):
    def test_confirmed_but_hole(self):
        found = checks.c6_tri_state([R("shifts.csv", 2, occurred_at="")], {"S001"})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].type, "缺失与未确认混同")

    def test_complete_row_silent(self):
        self.assertEqual(checks.c6_tri_state([R("shifts.csv", 2)], {"S001"}), [])

    def test_unconfirmed_row_not_double_counted(self):
        """未确认行由 C4 负责，C6 只管"已确认却有洞"，避免同一事实算两次。"""
        self.assertEqual(checks.c6_tri_state([R("shifts.csv", 2, confirm_status="unconfirmed", occurred_at="")], {"S001"}), [])


class C1OrphanTest(unittest.TestCase):
    def test_unplanned_checkin_is_a_field_fact(self):
        found = checks.c1_cross_check(
            [R("shifts.csv", 2, shift_id="S001")],
            [C("checkins.csv", 3, shift_id="S999", person_code="Z0009", site_id="S-A")],
            {},
            {"S001"},
        )
        types = [f.type for f in found]
        self.assertIn("计划外到岗", types)
        orphan = [f for f in found if f.type == "计划外到岗"][0]
        self.assertEqual(orphan.subject, "S999")
        self.assertIn("顶班", orphan.detail)
        self.assertIn("checkins.csv#L3", orphan.source_locator)

    def test_known_shift_is_not_an_orphan(self):
        found = checks.c1_cross_check(
            [R("shifts.csv", 2, shift_id="S001")],
            [C("checkins.csv", 2, shift_id="S001")],
            {},
            {"S001"},
        )
        self.assertNotIn("计划外到岗", [f.type for f in found])


class C7Test(unittest.TestCase):
    def test_duplicate_id(self):
        rows = [R("shifts.csv", 2), R("shifts.csv", 3)]
        found = checks.c7_numbering(rows, [], [])
        self.assertEqual(found[0].type, "重复编号")
        self.assertIn("shifts.csv#L2", found[0].source_locator)

    def test_checkin_orphan_is_not_reported_here(self):
        """签到侧孤儿引用由 C1 报"计划外到岗"：那是现场事实，不是编号问题（同一行不重复计数）。"""
        self.assertEqual(checks.c7_numbering([R("shifts.csv", 2)], [C("checkins.csv", 2, shift_id="S999")], []), [])

    def test_handover_orphan_is_reported_here(self):
        found = checks.c7_numbering([R("shifts.csv", 2)], [], [H("handover.csv", 2, shift_id="S999")])
        self.assertEqual([f.type for f in found], ["编号断链"])

    def test_unit_difference_hours_as_minutes(self):
        found = checks.c7_numbering([R("shifts.csv", 2, window_minutes="4")], [], [])
        self.assertEqual([f.type for f in found], ["单位差异"])
        self.assertIn("小时", found[0].detail)

    def test_inverted_window(self):
        found = checks.c7_numbering(
            [R("shifts.csv", 2, window_start="2026-10-03T11:00:00", window_end="2026-10-03T07:00:00")], [], []
        )
        self.assertIn("时间窗倒置", [f.type for f in found])

    def test_clean_row_silent(self):
        self.assertEqual(checks.c7_numbering([R("shifts.csv", 2)], [C("checkins.csv", 2)], []), [])


class C8Test(unittest.TestCase):
    def test_unavailable_snapshot_becomes_finding(self):
        snap = Snapshot(file_name="checkins.csv", path="/x", status="unavailable",
                        taken_at="2026-10-03T16:00:00", note="读取失败：FileNotFoundError")
        found = checks.c8_failure_marks([snap])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].type, "数据读取失败")
        self.assertIn("2026-10-03T16:00:00", found[0].detail)

    def test_ok_snapshot_silent(self):
        snap = Snapshot(file_name="checkins.csv", path="/x", status="ok", taken_at="t", sha256="abc", rows=3)
        self.assertEqual(checks.c8_failure_marks([snap]), [])


class C9Test(unittest.TestCase):
    def test_write_api_flagged(self):
        found = checks.c9_boundary(Boundary(write_apis=("crm",)))
        self.assertEqual(found[0].type, "能力越界")
        self.assertIn("write_apis", found[0].detail)

    def test_clean_boundary_silent(self):
        self.assertEqual(checks.c9_boundary(Boundary()), [])


if __name__ == "__main__":
    unittest.main()
