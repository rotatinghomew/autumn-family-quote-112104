"""分类解释、支出分布与敏感约束。"""
import unittest
from pathlib import Path

from source_book import load
from quoting.analyze import analyze, naive_calendar_sum
from quoting.assess import (
    STATUS_COMMITTABLE,
    STATUS_GUARANTEED,
    STATUS_INSUFFICIENT_EVIDENCE,
    STATUS_OVER_BUDGET,
    STATUS_STALLED,
)
from quoting.model import build_view

ROOT = Path(__file__).resolve().parents[1]


def assess_at(seq):
    view = build_view(load(ROOT / "data" / "samples.json"), seq)
    *_, assessments = analyze(view)
    return view, assessments


class AssessTest(unittest.TestCase):
    def test_round3_statuses(self):
        _, a = assess_at(3)
        self.assertEqual(a["h1"].status, STATUS_GUARANTEED)
        self.assertEqual(a["h2"].status, STATUS_GUARANTEED)
        self.assertEqual(a["h3"].status, STATUS_STALLED)  # o2 过期、s4 撤回
        self.assertEqual(a["h4"].status, STATUS_INSUFFICIENT_EVIDENCE)  # 只剩仅询价的 o6

    def test_round1_statuses(self):
        _, a = assess_at(1)
        self.assertEqual(a["h2"].status, STATUS_COMMITTABLE)
        self.assertEqual(a["h2"].committable["价格"], 333)
        self.assertEqual(a["h3"].status, STATUS_OVER_BUDGET)  # 最低 373 超预算 310
        self.assertEqual(a["h4"].status, STATUS_COMMITTABLE)
        self.assertEqual(a["h4"].committable["价格"], 373)

    def test_typical_spend_comes_from_joint_placement(self):
        _, a = assess_at(1)
        typical = a["h4"].typical
        self.assertEqual(typical["最低"], 373)
        self.assertEqual(typical["最高"], 415)
        self.assertTrue(typical["稳定"])

    def test_sensitivities_keep_binding_constraints(self):
        _, a = assess_at(3)
        h4_text = "\n".join(a["h4"].sensitivities)
        self.assertIn("撤至1", h4_text)  # s4 撤回
        self.assertIn("仅可询价", h4_text)  # o6
        h3_text = "\n".join(a["h3"].sensitivities)
        self.assertIn("已过期", h3_text)  # o2
        self.assertIn("改时", h3_text)  # 时段敏感

    def test_naive_calendar_sum_is_not_committable(self):
        view, a = assess_at(3)
        naive = naive_calendar_sum(view, view.family("h1"))
        self.assertEqual(naive, 250)  # 日历页低价合计
        self.assertEqual(a["h1"].committable["价格"], 420)  # 已受理保证的承诺价
        self.assertNotEqual(naive, a["h1"].typical["典型"])

    def test_open_quote_undeliverable_goes_manual(self):
        _, a = assess_at(3)
        self.assertTrue(a["h3"].manual)
        self.assertTrue(any("q3" in r for r in a["h3"].recontact))


if __name__ == "__main__":
    unittest.main()
