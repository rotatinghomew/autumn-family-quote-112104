"""接入后续团期：追加新轮次的报价与库存后同一引擎继续报价。"""
import json
import tempfile
import unittest
from pathlib import Path

from source_book import load
from quoting.analyze import analyze
from quoting.assess import STATUS_COMMITTABLE, STATUS_GUARANTEED, STATUS_OVER_BUDGET
from quoting.model import build_view

ROOT = Path(__file__).resolve().parents[1]


class NextRoundTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = json.loads((ROOT / "data" / "samples.json").read_text(encoding="utf-8"))
        # 第 4 轮：s4 补回 2 个确认库存；s2 新增可订报价 o7（限 1 大 1 小）
        raw["tables"]["inventory"]["rows"].append(["s4", 4, 2, 0])
        raw["tables"]["offers"]["rows"].append(["o7", "s2", 1, 1, 100, 20, 5, "可订"])
        cls._tmp = tempfile.TemporaryDirectory()
        path = Path(cls._tmp.name) / "round4.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        cls.view = build_view(load(path), 4)
        *_, cls.assessments = analyze(cls.view)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_accepted_guarantees_still_honored(self):
        self.assertEqual(self.assessments["h1"].status, STATUS_GUARANTEED)
        self.assertEqual(self.assessments["h2"].status, STATUS_GUARANTEED)

    def test_restocked_slot_makes_family_committable(self):
        h4 = self.assessments["h4"]
        self.assertEqual(h4.status, STATUS_COMMITTABLE)
        self.assertEqual(h4.committable["价格"], 415)  # o1 + o4

    def test_new_offer_changes_classification(self):
        h3 = self.assessments["h3"]
        self.assertEqual(h3.status, STATUS_OVER_BUDGET)  # o7+o4 = 380 仍超预算 310
        self.assertIn("380", "\n".join(h3.reasons))

    def test_expired_offer_stays_expired(self):
        offers = {o.offer: o for o in self.view.offers}
        self.assertFalse(offers["o3"].valid_at(4))  # o3 第 3 轮后失效
        self.assertTrue(offers["o1"].valid_at(4))


if __name__ == "__main__":
    unittest.main()
