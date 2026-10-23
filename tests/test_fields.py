import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volunteer_handover.core.fields import (  # noqa: E402
    KEY_FIELDS,
    Tri,
    is_confirmed,
    missing_key_fields,
    tri,
)


class TriStateTest(unittest.TestCase):
    def test_empty_is_missing_not_unconfirmed(self):
        """空字符串是"缺失"，绝不能算"未确认"——两者混同会让追溯失真（f31）。"""
        self.assertIs(tri(""), Tri.MISSING)
        self.assertIs(tri(None), Tri.MISSING)
        self.assertIs(tri("   "), Tri.MISSING)

    def test_unconfirmed_token(self):
        self.assertIs(tri("未确认"), Tri.UNCONFIRMED)
        self.assertIs(tri("待确认"), Tri.UNCONFIRMED)
        self.assertIs(tri("unconfirmed"), Tri.UNCONFIRMED)

    def test_present(self):
        self.assertIs(tri("Z0001"), Tri.PRESENT)
        self.assertIs(tri(0), Tri.PRESENT)

    def test_missing_key_fields_reports_state(self):
        holes = missing_key_fields({"person_code": "Z1", "position_id": "", "skill_tags": "未确认",
                                    "window_start": "2026-01-01T00:00:00", "confirm_status": "confirmed"})
        names = dict(holes)
        self.assertIs(names["position_id"], Tri.MISSING)
        self.assertIs(names["skill_tags"], Tri.UNCONFIRMED)
        self.assertNotIn("person_code", names)

    def test_key_fields_cover_contract(self):
        for name in ("person_code", "position_id", "skill_tags", "window", "confirm_status"):
            self.assertIn(name, KEY_FIELDS)

    def test_is_confirmed(self):
        self.assertTrue(is_confirmed("confirmed"))
        self.assertTrue(is_confirmed("已确认"))
        self.assertFalse(is_confirmed("unconfirmed"))
        self.assertFalse(is_confirmed(""))


if __name__ == "__main__":
    unittest.main()
