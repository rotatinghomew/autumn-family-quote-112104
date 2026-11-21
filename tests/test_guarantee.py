"""书面保价签发：授权、库存与有效期校验。"""
import unittest
from pathlib import Path

from source_book import load
from quoting.guarantee import issue_guarantee
from quoting.model import build_view

ROOT = Path(__file__).resolve().parents[1]


def view_at(seq):
    return build_view(load(ROOT / "data" / "samples.json"), seq)


class IssueTest(unittest.TestCase):
    def test_issue_valid_guarantee(self):
        decision = issue_guarantee(view_at(1), "h4", [["o2", "o4"]], 380)
        self.assertTrue(decision.ok)
        self.assertEqual(decision.valid_until, 2)  # o2 第 2 轮后失效
        self.assertEqual(decision.compensation_reserved, 0)
        self.assertEqual(decision.quote_row["options"], [["o2", "o4"]])
        self.assertFalse(decision.quote_row["accepted"])

    def test_reject_inquiry_only_option(self):
        decision = issue_guarantee(view_at(3), "h4", [["o1", "o6"]], 260)
        self.assertFalse(decision.ok)
        self.assertTrue(any("仅可询价" in r for r in decision.reasons))

    def test_reject_expired_offer(self):
        decision = issue_guarantee(view_at(3), "h4", [["o2", "o4"]], 380)
        self.assertFalse(decision.ok)
        self.assertTrue(any("失效" in r for r in decision.reasons))

    def test_reject_when_accepted_guarantees_took_inventory(self):
        # 第 3 轮 s4 已被 q1 的受理保证预留
        decision = issue_guarantee(view_at(3), "h4", [["o1", "o4"]], 420)
        self.assertFalse(decision.ok)
        self.assertTrue(any("s4" in r for r in decision.reasons))

    def test_reject_subsidy_beyond_authority(self):
        # 成本 415，承诺 300，需补差 115 超出第 1 轮限额 80
        decision = issue_guarantee(view_at(1), "h4", [["o1", "o4"]], 300)
        self.assertFalse(decision.ok)
        self.assertTrue(any("补差" in r for r in decision.reasons))

    def test_reject_duplicate_for_guaranteed_family(self):
        decision = issue_guarantee(view_at(3), "h1", [["o1", "o4"]], 420)
        self.assertFalse(decision.ok)

    def test_multiple_options_checked_individually(self):
        # 两个备选各自可行即可签发，家庭只算一份需求
        decision = issue_guarantee(view_at(1), "h2", [["o2", "o5"], ["o1", "o4"]], 420)
        self.assertTrue(decision.ok)
        self.assertEqual(decision.valid_until, 4)
        self.assertEqual(len(decision.quote_row["options"]), 2)


if __name__ == "__main__":
    unittest.main()
