import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volunteer_handover.core import configschema  # noqa: E402
from volunteer_handover.utils import config as cfg  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "config" / "default.yaml"


class ValidConfigTest(unittest.TestCase):
    def test_shipped_config_is_valid(self):
        self.assertEqual(configschema.validate(cfg.load(DEFAULT)), [])

    def test_empty_config_is_valid(self):
        self.assertEqual(configschema.validate({}), [])


class UnknownKeyTest(unittest.TestCase):
    def test_typo_in_key_is_blocked_with_suggestion(self):
        problems = configschema.validate({"pilot": {"page_item_limt": 40}})
        self.assertEqual(len(problems), 1)
        self.assertIn("page_item_limt", problems[0])
        self.assertIn("page_item_limit", problems[0])  # 要指出来，别让人去猜

    def test_typo_in_section(self):
        problems = configschema.validate({"pilots": {"batch_id": "B"}})
        self.assertTrue(any("pilots" in p for p in problems))

    def test_scalar_top_level_is_not_a_section(self):
        problems = configschema.validate({"batch_id": "B"})
        self.assertTrue(problems)

    def test_unknown_anomaly_type_would_silently_drop_a_whole_class(self):
        problems = configschema.validate(
            {"scope": {"allowed_anomaly_types": ["缺岗未登记", "缺岗未登计"]}}
        )
        self.assertTrue(any("未知异常类型" in p and "缺岗未登计" in p for p in problems))


class TypeTest(unittest.TestCase):
    def test_string_where_int_expected(self):
        problems = configschema.validate({"output": {"max_page_items": "40"}})
        self.assertTrue(any("应该是整数" in p for p in problems))

    def test_bool_where_int_expected(self):
        problems = configschema.validate({"pilot": {"page_item_limit": True}})
        self.assertTrue(any("应该是整数" in p for p in problems))

    def test_string_where_bool_expected(self):
        problems = configschema.validate({"versions": {"require_confirm_status": "false"}})
        self.assertTrue(any("true/false" in p for p in problems))

    def test_list_where_scalar_expected(self):
        problems = configschema.validate({"scope": {"excluded_position_categories": "医疗"}})
        self.assertTrue(any("应该是列表" in p for p in problems))

    def test_non_positive_page_limit(self):
        problems = configschema.validate({"output": {"max_page_items": 0}})
        self.assertTrue(any("大于 0" in p for p in problems))

    def test_unparseable_as_of(self):
        problems = configschema.validate({"time": {"as_of": "十月三号下午"}})
        self.assertTrue(any("无法解析" in p for p in problems))

    def test_null_threshold_is_allowed(self):
        self.assertEqual(configschema.validate({"time": {"backfill_threshold_minutes": None}}), [])


class ModeTest(unittest.TestCase):
    def test_only_readonly_mode_exists(self):
        self.assertEqual(configschema.validate({"project": {"mode": "readonly"}}), [])
        problems = configschema.validate({"project": {"mode": "readwrite"}})
        self.assertTrue(any("只读" in p or "readonly" in p for p in problems))


class DescribeTest(unittest.TestCase):
    def test_describe_says_no_conclusion(self):
        text = configschema.describe(["未知配置项 `a.b`"])
        self.assertIn("不出结论", text)
        self.assertIn("a.b", text)


if __name__ == "__main__":
    unittest.main()
