"""整程组合枚举与报价适用性。"""
import unittest
from pathlib import Path

from source_book import load
from quoting.model import build_view
from quoting.plan import BLOCK_INQUIRY, BLOCK_INCOMPLETE, BLOCK_TIMING, enumerate_plan, resolve_option

ROOT = Path(__file__).resolve().parents[1]


class PlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = build_view(load(ROOT / "data" / "samples.json"), 3)

    def test_only_bookable_valid_offers_enter_combos(self):
        plan = enumerate_plan(self.view, self.view.family("h1"))
        self.assertEqual([c.offers for c in plan.combos], [("o1", "o4")])
        self.assertEqual(plan.combos[0].total, 415)

    def test_inquiry_only_offer_is_blocked_not_priced(self):
        plan = enumerate_plan(self.view, self.view.family("h4"))
        blocked = {tuple(s.slot for s in slots): [b.kind for b in bs] for slots, bs in plan.blocked}
        self.assertIn(("s1", "s5"), blocked)
        self.assertIn(BLOCK_INQUIRY, blocked[("s1", "s5")])  # o6 仅询价
        self.assertNotIn(("o1", "o6"), [c.offers for c in plan.combos])

    def test_expired_offer_blocks_combo(self):
        plan = enumerate_plan(self.view, self.view.family("h3"))
        self.assertEqual(plan.combos, [])  # o2 已过期，s2 没有可订报价
        kinds = [b.kind for _, bs in plan.blocked for b in bs]
        self.assertIn("报价已过期", kinds)

    def test_party_cap_blocks_combo(self):
        # o5 限 1 名儿童，h4 有 2 名；(s1,s5) 只能走仅询价的 o6
        plan = enumerate_plan(self.view, self.view.family("h4"))
        self.assertNotIn(("o1", "o5"), [c.offers for c in plan.combos])

    def test_combos_are_complete(self):
        for family in self.view.families:
            plan = enumerate_plan(self.view, family)
            for combo in plan.combos:
                stations = {leg.slot.station for leg in combo.legs}
                self.assertEqual(stations, {"访馆", "实践"})

    def test_resolve_option_checks(self):
        view = self.view
        h3 = view.family("h3")
        combo, problems = resolve_option(view, h3, ["o1", "o3"])
        self.assertIsNone(combo)  # 时段不可行：需改时 70 分钟
        self.assertIn(BLOCK_TIMING, [p.kind for p in problems])
        combo, problems = resolve_option(view, h3, ["o1", "o2"])
        self.assertIsNone(combo)  # 同站重复且 o2 过期
        self.assertIn(BLOCK_INCOMPLETE, [p.kind for p in problems])
        combo, _ = resolve_option(view, view.family("h1"), ["o1", "o4"])
        self.assertEqual(combo.total, 415)


if __name__ == "__main__":
    unittest.main()
