"""表头契约：缺必需列必须挡下来，缺可选列必须显式说"这项判断跳过了"。"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from volunteer_handover.core.engine import run  # noqa: E402
from volunteer_handover.core.loader import load_dataset  # noqa: E402
from volunteer_handover.core.schema import (  # noqa: E402
    FILE_SCHEMAS,
    check_columns,
    required_columns,
)


def _clone_data(drop_column: str, file_name: str = "shifts.csv") -> str:
    """复制样本数据，然后从指定文件里删掉一列。"""
    tmp = tempfile.mkdtemp(prefix="vh-schema-")
    for name in ("positions.csv", "shifts.csv", "checkins.csv", "handover.csv"):
        shutil.copy(ROOT / "data" / name, Path(tmp) / name)
    target = Path(tmp) / file_name
    lines = target.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    idx = header.index(drop_column)
    out = [",".join(h for i, h in enumerate(header) if i != idx)]
    for line in lines[1:]:
        cells = line.split(",")
        out.append(",".join(c for i, c in enumerate(cells) if i != idx))
    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    return tmp


class CheckColumnsTest(unittest.TestCase):
    def test_full_header_is_ok(self):
        check = check_columns("shifts.csv", FILE_SCHEMAS["shifts.csv"]["required"])
        self.assertTrue(check.ok)
        self.assertEqual(check.missing_required, ())

    def test_missing_required_is_reported_with_reason(self):
        check = check_columns("positions.csv", ["position_id", "site_id"])
        self.assertFalse(check.ok)
        self.assertIn("category", check.missing_required)
        self.assertIn("医疗/安保", check.describe())

    def test_missing_optional_does_not_block(self):
        check = check_columns("checkins.csv", ["checkin_id", "shift_id", "person_code",
                                               "occurred_at", "received_at", "source_tool"])
        self.assertTrue(check.ok)
        self.assertIn("site_id", check.missing_optional)
        self.assertIn("跳过", check.describe())

    def test_required_columns_helper(self):
        self.assertIn("confirm_status", required_columns("shifts.csv"))


class LoaderColumnTest(unittest.TestCase):
    def tearDown(self):
        for attr in ("_tmp",):
            value = getattr(self, attr, None)
            if value:
                shutil.rmtree(value, ignore_errors=True)

    def test_dataset_flags_blocked_columns(self):
        self._tmp = _clone_data("confirm_status")
        dataset = load_dataset(self._tmp)
        self.assertTrue(any(c.file_name == "shifts.csv" for c in dataset.blocked_columns()))

    def test_optional_missing_produces_warning_not_block(self):
        self._tmp = _clone_data("site_id", "checkins.csv")
        dataset = load_dataset(self._tmp)
        self.assertEqual(dataset.blocked_columns(), [])
        warnings = dataset.column_warnings()
        self.assertTrue(any("site_id" in w for w in warnings))
        self.assertTrue(any("不等于" in w for w in warnings))


class EngineBlockedByColumnsTest(unittest.TestCase):
    def test_missing_required_column_blocks_run(self):
        tmp = _clone_data("window_end")
        try:
            result = run(tmp, {})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertTrue(result.blocked)
        self.assertIn("表头契约", result.blocked_reason)
        self.assertIn("window_end", result.blocked_reason)

    def test_blocked_reason_says_it_is_not_a_conclusion(self):
        tmp = _clone_data("person_code", "checkins.csv")
        try:
            result = run(tmp, {})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertIn("本次不出结论", result.blocked_reason)


if __name__ == "__main__":
    unittest.main()
