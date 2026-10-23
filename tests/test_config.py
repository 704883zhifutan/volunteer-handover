import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volunteer_handover.utils import config as cfg  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class ConfigParseTest(unittest.TestCase):
    def test_nested_and_scalars(self):
        parsed = cfg.parse(
            "a:\n  b: 1\n  c: true\nd: null\ne: '文本'\nf: []\n"
        )
        self.assertEqual(parsed["a"], {"b": 1, "c": True})
        self.assertIsNone(parsed["d"])
        self.assertEqual(parsed["e"], "文本")
        self.assertEqual(parsed["f"], [])

    def test_list_of_scalars_and_maps(self):
        parsed = cfg.parse("items:\n  - 甲\n  - 乙\nmaps:\n  - k: 1\n    j: 2\n")
        self.assertEqual(parsed["items"], ["甲", "乙"])
        self.assertEqual(parsed["maps"], [{"k": 1, "j": 2}])

    def test_comment_and_inline_hash_in_quotes(self):
        parsed = cfg.parse('a: "x # y"  # 注释\n')
        self.assertEqual(parsed["a"], "x # y")

    def test_tab_rejected(self):
        with self.assertRaises(cfg.ConfigError):
            cfg.parse("a:\n\tb: 1\n")

    def test_bad_indent_rejected(self):
        with self.assertRaises(cfg.ConfigError):
            cfg.parse("a: 1\n    b: 2\n")

    def test_get_dotted(self):
        self.assertEqual(cfg.get({"a": {"b": 3}}, "a.b"), 3)
        self.assertEqual(cfg.get({"a": {}}, "a.b.c", "默认"), "默认")

    def test_shipped_config_loads(self):
        loaded = cfg.load(ROOT / "config" / "default.yaml")
        self.assertEqual(loaded["project"]["mode"], "readonly")
        self.assertIsNone(loaded["time"]["backfill_threshold_minutes"])
        self.assertIn("医疗", loaded["scope"]["excluded_position_categories"])
        self.assertEqual(loaded["boundary"]["write_apis"], [])


if __name__ == "__main__":
    unittest.main()
