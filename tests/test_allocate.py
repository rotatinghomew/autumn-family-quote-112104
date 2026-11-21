"""联合安置：受理保证优先、撤回改派、灵活家庭不抢唯一场次。"""
import unittest
from pathlib import Path

from source_book import load
from quoting.allocate import Placement, enumerate_assignments, honor_accepted
from quoting.model import build_view
from quoting.plan import Combo, Leg

ROOT = Path(__file__).resolve().parents[1]


def synthetic_book():
    return {
        "families": [
            {"family": "hard", "adults": 2, "children": 1, "start": "09:00", "end": "11:30", "budget": 500, "flexible_time": 0},
            {"family": "flex", "adults": 2, "children": 1, "start": "09:00", "end": "14:00", "budget": 500, "flexible_time": 0},
        ],
        "products": [
            {"slot": "v1", "station": "访馆", "start": "09:00", "end": "10:00", "travel_to_next_min": 0},
            {"slot": "p1", "station": "实践", "start": "10:30", "end": "11:30", "travel_to_next_min": 0},
            {"slot": "p2", "station": "实践", "start": "13:00", "end": "14:00", "travel_to_next_min": 0},
        ],
        "offers": [
            {"offer": "ov", "slot": "v1", "adults": 2, "children": 2, "base": 100, "required_fee": 0, "expires": 9, "certainty": "可订"},
            {"offer": "op1", "slot": "p1", "adults": 2, "children": 2, "base": 100, "required_fee": 0, "expires": 9, "certainty": "可订"},
            {"offer": "op2", "slot": "p2", "adults": 2, "children": 2, "base": 120, "required_fee": 0, "expires": 9, "certainty": "可订"},
        ],
        "inventory": [
            {"slot": "v1", "seq": 1, "confirmed": 2, "ambiguous": 0},
            {"slot": "p1", "seq": 1, "confirmed": 1, "ambiguous": 0},
            {"slot": "p2", "seq": 1, "confirmed": 1, "ambiguous": 0},
        ],
        "quotes": [
            {"quote": "qa", "family": "hard", "options": [["ov", "op1"]], "locked": ["ov", "op1"], "promised": 200, "accepted": True, "seq": 1},
            {"quote": "qb", "family": "flex", "options": [["ov", "op1"], ["ov", "op2"]], "locked": ["ov", "op1"], "promised": 200, "accepted": True, "seq": 1},
        ],
        "authority": [{"seq": 1, "compensation_limit": 50}],
    }


class HonorAcceptedTest(unittest.TestCase):
    def test_sample_round3_rebooks_within_accepted_range(self):
        view = build_view(load(ROOT / "data" / "samples.json"), 3)
        honored, remaining, relief, manual = honor_accepted(view)
        self.assertEqual(honored["q1"].placement.combo.offers, ("o1", "o4"))
        self.assertFalse(honored["q1"].placement.changed)
        # o2 已过期，q2 在接受范围内改派 [o1,o5]，差价 0
        self.assertEqual(honored["q2"].placement.combo.offers, ("o1", "o5"))
        self.assertTrue(honored["q2"].placement.changed)
        self.assertEqual(honored["q2"].placement.compensation, 0)
        self.assertEqual(honored["q2"].family_pays, 375)
        self.assertEqual(relief, 0)
        self.assertEqual(manual, [])
        self.assertEqual(remaining["s4"], 0)
        self.assertEqual(remaining["s5"], 1)

    def test_joint_placement_protects_inflexible_family(self):
        # p1 只剩 1 个：逐单保锁定会让后到的 hard 无家可安，联合安置应让 flex 改去 p2
        view = build_view(synthetic_book(), 1)
        honored, remaining, relief, manual = honor_accepted(view)
        self.assertEqual(manual, [])
        self.assertEqual(honored["qa"].placement.combo.offers, ("ov", "op1"))
        self.assertFalse(honored["qa"].placement.changed)
        self.assertEqual(honored["qb"].placement.combo.offers, ("ov", "op2"))
        self.assertTrue(honored["qb"].placement.changed)
        # 改派差价 20 元由运营承担，家庭仍付承诺价
        self.assertEqual(honored["qb"].placement.compensation, 20)
        self.assertEqual(honored["qb"].family_pays, 200)
        self.assertEqual(relief, 20)
        self.assertEqual(remaining, {"v1": 0, "p1": 0, "p2": 0})

    def test_unplaceable_accepted_quote_goes_manual(self):
        book = synthetic_book()
        book["inventory"] = [
            {"slot": "v1", "seq": 1, "confirmed": 2, "ambiguous": 0},
            {"slot": "p1", "seq": 1, "confirmed": 1, "ambiguous": 0},
            {"slot": "p2", "seq": 1, "confirmed": 0, "ambiguous": 0},
        ]
        view = build_view(book, 1)
        _, _, _, manual = honor_accepted(view)
        self.assertTrue(any(entry["报价"] == "qb" for entry in manual))


class AssignmentTest(unittest.TestCase):
    def _combo(self, view, offer_ids):
        legs = tuple(Leg(view.slot(view.offer(o).slot), view.offer(o)) for o in offer_ids)
        return Combo(legs, sum(leg.offer.price for leg in legs), 0)

    def test_multiple_options_count_as_one_demand(self):
        # 同一家庭的两个备选不能同时扣掉两个名额
        view = build_view(synthetic_book(), 1)
        combo_a = self._combo(view, ["ov", "op1"])
        combo_b = self._combo(view, ["ov", "op2"])
        candidates = {"fam": [Placement(combo_a, 0, False), Placement(combo_b, 0, False)]}
        assignments = enumerate_assignments(candidates, {"v1": 1, "p1": 1, "p2": 1})
        self.assertTrue(assignments)
        for assignment in assignments:
            used = [s for p in assignment.values() for s in p.combo.slots]
            self.assertEqual(len(used), len(set(used)))
            self.assertLessEqual(used.count("v1"), 1)

    def test_competing_families_share_scarce_slot(self):
        view = build_view(synthetic_book(), 1)
        combo_a = self._combo(view, ["ov", "op1"])
        combo_b = self._combo(view, ["ov", "op2"])
        candidates = {
            "f1": [Placement(combo_a, 0, False), Placement(combo_b, 0, False)],
            "f2": [Placement(combo_a, 0, False), Placement(combo_b, 0, False)],
        }
        assignments = enumerate_assignments(candidates, {"v1": 1, "p1": 1, "p2": 1})
        self.assertTrue(all(len(a) == 1 for a in assignments))  # v1 只有 1 个

    def test_contested_combo_is_not_stable(self):
        # 唯一可行组合可能被同批用尽时，不能当作确定的预计支出
        from quoting.allocate import competition
        from quoting.plan import enumerate_plan

        book = synthetic_book()
        book["quotes"] = []
        book["inventory"] = [
            {"slot": "v1", "seq": 1, "confirmed": 1, "ambiguous": 0},
            {"slot": "p1", "seq": 1, "confirmed": 1, "ambiguous": 0},
            {"slot": "p2", "seq": 1, "confirmed": 1, "ambiguous": 0},
        ]
        view = build_view(book, 1)
        plans = {f.family: enumerate_plan(view, f) for f in view.families}
        remaining = {"v1": 1, "p1": 1, "p2": 1}
        info = competition(view, plans, remaining)
        self.assertTrue(info["hard"]["可安置"])
        self.assertFalse(info["hard"]["稳定"])  # 有的联合方案里 hard 被挤掉
        self.assertFalse(info["flex"]["稳定"])


if __name__ == "__main__":
    unittest.main()
