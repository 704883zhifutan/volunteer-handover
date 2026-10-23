import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volunteer_handover.core.engine import run, write_outputs  # noqa: E402
from volunteer_handover.main import main  # noqa: E402
from volunteer_handover.utils import config as cfg  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "default.yaml"


class EngineGoldenTest(unittest.TestCase):
    """样本数据是金标：数字变了就说明逻辑变了，必须显式更新这里。"""

    @classmethod
    def setUpClass(cls):
        cls.config = cfg.load(CONFIG)
        cls.result = run(DATA, cls.config)

    def test_golden_counts(self):
        self.assertEqual(len(self.result.items.findings), 20)
        self.assertEqual(len(self.result.checks), 3)
        self.assertEqual(len(self.result.excluded_shifts), 2)

    def test_every_finding_is_traceable(self):
        for finding in self.result.items.findings:
            self.assertTrue(finding.source_locator, f"缺 locator：{finding.type}")
            self.assertRegex(finding.source_locator, r"#L\d+|快照|config/")

    def test_every_suggestion_is_advisory_only(self):
        for finding in self.result.items.findings:
            self.assertTrue(finding.suggestion.startswith("仅提示"), finding.suggestion)
            self.assertEqual(finding.review_status, "未复核")

    def test_expected_types_present(self):
        types = {f.type for f in self.result.items.findings}
        for expected in ("缺岗未登记", "疑似重复占位", "排班表与现场不一致",
                         "版本断链或过期", "版本未确认", "缺失与未确认混同",
                         "编号断链", "单位差异", "时间倒挂", "疑似回填"):
            self.assertIn(expected, types)

    def test_out_of_scope_excludes_medical_and_security(self):
        joined = " ".join(self.result.excluded_shifts)
        self.assertIn("医疗", joined)
        self.assertIn("安保", joined)

    def test_not_blocked_and_no_missing_files(self):
        self.assertFalse(self.result.blocked)
        self.assertEqual(self.result.dataset.missing, [])

    def test_snapshots_cover_all_files(self):
        names = {s.file_name for s in self.result.dataset.snapshots}
        self.assertEqual(names, {"positions.csv", "shifts.csv", "checkins.csv", "handover.csv"})
        for snap in self.result.dataset.snapshots:
            self.assertEqual(snap.status, "ok")
            self.assertTrue(snap.sha256)


class OutputTest(unittest.TestCase):
    def setUp(self):
        self.config = cfg.load(CONFIG)
        self.tmp = tempfile.mkdtemp()

    def test_outputs_written(self):
        result = run(DATA, self.config)
        paths = write_outputs(result, self.tmp)
        for path in paths.values():
            self.assertTrue(Path(path).exists(), path)
        items_md = paths["items_md"].read_text(encoding="utf-8")
        self.assertIn("待人工复核的建议", items_md)
        handover_md = paths["handover_md"].read_text(encoding="utf-8")
        self.assertIn("待确认", handover_md)  # “完成”定义未确认，必须留白

    def test_page_limit_produces_warning_not_extra_pages(self):
        self.config["output"]["max_page_items"] = 5
        result = run(DATA, self.config)
        self.assertTrue(any("超过一页上限" in w for w in result.warnings))

    def test_missing_file_does_not_crash_and_is_marked(self):
        config = dict(self.config)
        with tempfile.TemporaryDirectory() as empty:
            result = run(empty, config)
        self.assertEqual(len(result.dataset.missing), 4)
        self.assertTrue(any(f.type == "数据读取失败" for f in result.items.findings))
        self.assertTrue(result.warnings)


class BlockedTest(unittest.TestCase):
    def test_write_api_blocks_run(self):
        config = cfg.load(CONFIG)
        config["boundary"]["write_apis"] = ["crm"]
        result = run(DATA, config)
        self.assertTrue(result.blocked)
        self.assertIn("write_apis", result.blocked_reason)
        self.assertTrue(any(f.type == "能力越界" for f in result.items.findings))


class CliTest(unittest.TestCase):
    def test_cli_exit_zero(self):
        with tempfile.TemporaryDirectory() as out, redirect_stdout(io.StringIO()) as buf:
            code = main(["--out", out, "--max-print", "3"])
        self.assertEqual(code, 0)
        self.assertIn("只读核对完成", buf.getvalue())

    def test_cli_exit_two_on_boundary_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_text(
                "pilot:\n  batch_id: B\nboundary:\n  write_apis:\n    - crm\n",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()) as buf:
                code = main(["--config", str(path), "--out", tmp, "--max-print", "0"])
        self.assertEqual(code, 2)
        self.assertIn("运行被阻断", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
