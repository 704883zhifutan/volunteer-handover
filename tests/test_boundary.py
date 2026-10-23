import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volunteer_handover.core import boundary as bd  # noqa: E402
from volunteer_handover.core import engine  # noqa: E402


class GuardTest(unittest.TestCase):
    def test_every_forbidden_capability_raises(self):
        boundary = bd.Boundary()
        for cap in bd.FORBIDDEN_CAPABILITIES:
            with self.assertRaises(bd.BoundaryViolation):
                boundary.guard(cap)

    def test_read_is_allowed(self):
        bd.Boundary().guard("read_csv")

    def test_violations_reported(self):
        boundary = bd.Boundary(write_apis=("crm",), outbound_channel="sms",
                               auto_assign_categories=("医疗",))
        keys = [k for k, _ in boundary.violations()]
        self.assertEqual(keys, ["write_apis", "outbound_channel", "auto_assign_categories"])

    def test_empty_boundary_clean(self):
        self.assertEqual(bd.Boundary().violations(), [])

    def test_from_config_normalises(self):
        boundary = bd.Boundary.from_config({"write_apis": None, "outbound_channel": None})
        self.assertEqual(boundary.write_apis, ())
        self.assertEqual(boundary.violations(), [])


class NoWriteChannelTest(unittest.TestCase):
    def test_engine_module_has_no_network_stack(self):
        """只读工具不该引入任何外发能力：连 import 都不该出现。"""
        source = Path(engine.__file__).read_text(encoding="utf-8")
        for forbidden in ("requests", "urllib", "smtplib", "http.client", "socket"):
            self.assertNotIn(f"import {forbidden}", source)
            self.assertNotIn(f"from {forbidden}", source)

    def test_run_result_exposes_no_action_api(self):
        for name in ("apply", "commit", "send", "notify", "assign", "write_back", "approve"):
            self.assertFalse(hasattr(engine.RunResult, name), name)


if __name__ == "__main__":
    unittest.main()
