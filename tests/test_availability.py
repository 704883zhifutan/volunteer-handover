"""回归测试：输入不可读时，不允许"没读到"被当成"没有"。

这一条是 F9（假状态）里最隐蔽的一种：签到文件读失败，如果照常跑 C1，
每条排班都会因为"找不到签到"而被报成缺岗——数字涨了，人反而被误导。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from volunteer_handover.core import checks  # noqa: E402
from volunteer_handover.core.engine import run  # noqa: E402
from volunteer_handover.core.loader import Dataset, load_dataset  # noqa: E402
from volunteer_handover.utils import config as config_util  # noqa: E402

DATA = ROOT / "data"


class DatasetAvailabilityTest(unittest.TestCase):
    def test_available_true_when_file_read(self):
        dataset = load_dataset(DATA)
        self.assertTrue(dataset.available("checkins.csv"))

    def test_available_false_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = load_dataset(tmp)
            self.assertFalse(dataset.available("checkins.csv"))
            self.assertEqual(dataset.get("checkins.csv"), [])

    def test_zero_rows_is_available(self):
        """读到 0 行是"读了但没数据"，与"没读到"必须区分。"""
        dataset = Dataset(root="x")
        dataset.rows["checkins.csv"] = []
        self.assertTrue(dataset.available("checkins.csv"))


class NoPhantomAbsenceTest(unittest.TestCase):
    def setUp(self):
        self.config = config_util.load(ROOT / "config" / "default.yaml")
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        for name in ("positions.csv", "shifts.csv", "handover.csv"):
            shutil.copy(DATA / name, self.data / name)
        # 故意不放 checkins.csv

    def tearDown(self):
        self.tmp.cleanup()

    def test_c1_skipped_without_checkins(self):
        result = run(self.data, self.config)
        types = [f.type for f in result.items.findings]
        self.assertNotIn("缺岗未登记", types, "签到不可读时不得报缺岗")
        self.assertNotIn("排班表与现场不一致", types)
        self.assertIn("数据读取失败", types, "但仍要如实报告某文件没读到")

    def test_warning_says_missing_is_not_absent(self):
        result = run(self.data, self.config)
        joined = " ".join(result.warnings)
        self.assertIn("签到记录不可读", joined)
        self.assertIn("不等于没有缺岗", joined)

    def test_other_checks_still_run(self):
        """只跳过依赖签到的那条，其余校验照常——不因一个文件失败就全体静默。"""
        result = run(self.data, self.config)
        types = set(f.type for f in result.items.findings)
        self.assertIn("疑似重复占位", types)
        self.assertIn("版本未确认", types)
        self.assertEqual(len(result.checks), 3, "交接清单不依赖签到")

    def test_all_checks_returns_c8_for_missing_file(self):
        dataset = load_dataset(self.data)
        findings = checks.all_checks(
            dataset,
            {r.get("position_id"): r for r in dataset.get("positions.csv")},
            {r.get("shift_id") for r in dataset.get("shifts.csv")},
            __import__("volunteer_handover.core.boundary", fromlist=["Boundary"]).Boundary(),
            self.config,
        )
        c8 = [f for f in findings if f.code == "C8"]
        self.assertEqual(len(c8), 1)


if __name__ == "__main__":
    unittest.main()
