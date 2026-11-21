"""时段、接驳与改时分钟的核对。"""
import unittest
from pathlib import Path

from source_book import load
from quoting.model import build_view, parse_time, format_time
from quoting.plan import slot_combinations
from quoting.timeline import check_timing

ROOT = Path(__file__).resolve().parents[1]


class TimelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = build_view(load(ROOT / "data" / "samples.json"), 3)

    def test_parse_and_format(self):
        self.assertEqual(parse_time("09:30"), 570)
        self.assertEqual(format_time(570), "09:30")

    def test_transfer_shortfall_consumes_flex(self):
        view = self.view
        h3 = view.family("h3")  # 改时 30 分钟
        s1, s3 = view.slot("s1"), view.slot("s3")
        timing = check_timing(h3, (s1, s3))
        self.assertEqual(timing.transfer_shortfall, 10)  # 通行 30 分钟，空档只有 20 分钟
        self.assertEqual(timing.window_shortfall, 60)  # 09:30 早于窗口 10:30
        self.assertFalse(timing.feasible_for(h3))
        h2 = view.family("h2")  # 改时 90 分钟
        self.assertTrue(check_timing(h2, (s1, s3)).feasible_for(h2))

    def test_window_overflow_uses_flex_exactly(self):
        view = self.view
        h4 = view.family("h4")  # 改时 60 分钟，窗口到 16:00
        timing = check_timing(h4, (view.slot("s1"), view.slot("s5")))  # 17:00 结束
        self.assertEqual(timing.needed_flex, 60)
        self.assertTrue(timing.feasible_for(h4))
        h3 = view.family("h3")
        self.assertFalse(check_timing(h3, (view.slot("s2"), view.slot("s5"))).feasible_for(h3))

    def test_overlapping_slots_are_not_combinable(self):
        combos = {tuple(s.slot for s in combo) for combo in slot_combinations(self.view)}
        self.assertNotIn(("s2", "s3"), combos)  # s3 开始时 s2 尚未结束
        self.assertIn(("s1", "s4"), combos)


if __name__ == "__main__":
    unittest.main()
