"""客服查询视图的四要素区分。"""
import unittest
from pathlib import Path

from source_book import load
from quoting.analyze import service_views
from quoting.model import build_view

ROOT = Path(__file__).resolve().parents[1]


class ServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.views = service_views(build_view(load(ROOT / "data" / "samples.json"), 3))

    def test_four_aspects_present_for_every_family(self):
        for view in self.views.values():
            for key in ("典型支出", "目前可承诺", "已发保证", "需要重新联系"):
                self.assertIn(key, view)

    def test_rebooked_guarantee_needs_recontact(self):
        h2 = self.views["h2"]
        guarantee = h2["已发保证"][0]
        self.assertEqual(guarantee["状态"], "已受理·改派")
        self.assertEqual(guarantee["现组合"], ["o1", "o5"])
        self.assertEqual(guarantee["家庭应付"], 375)
        self.assertTrue(h2["需要重新联系"]["需要"])

    def test_honored_guarantee_is_distinct_from_estimate(self):
        h1 = self.views["h1"]
        self.assertEqual(h1["已发保证"][0]["承诺"], 420)
        self.assertEqual(h1["典型支出"]["典型"], 415)

    def test_stalled_family_goes_manual_with_reason(self):
        h3 = self.views["h3"]
        self.assertEqual(h3["状态"], "暂不成交")
        self.assertIsNone(h3["目前可承诺"])
        self.assertTrue(h3["转人工"])
        self.assertEqual(h3["已发保证"][0]["状态"], "待受理·无法兑现")

    def test_insufficient_evidence_family_waits_without_committable(self):
        h4 = self.views["h4"]
        self.assertEqual(h4["状态"], "证据不足")
        self.assertIsNone(h4["目前可承诺"])
        self.assertFalse(h4["需要重新联系"]["需要"])


if __name__ == "__main__":
    unittest.main()
