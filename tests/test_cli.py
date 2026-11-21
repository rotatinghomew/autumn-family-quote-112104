"""命令行冒烟测试：报告、客服查询与签发回写。"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*argv):
    return subprocess.run(
        [sys.executable, "-m", "quoting", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class CliTest(unittest.TestCase):
    def test_report(self):
        result = run_cli("report", "data/samples.json", "--seq", "3")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["家庭评估"]["h4"]["状态"], "证据不足")
        self.assertEqual(payload["剩余库存"]["s4"], 0)

    def test_service_single_family(self):
        result = run_cli("service", "data/samples.json", "--seq", "3", "--family", "h2")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["已发保证"][0]["状态"], "已受理·改派")

    def test_issue_writes_new_book(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "issued.json"
            result = run_cli(
                "issue", "data/samples.json", "--seq", "1",
                "--family", "h4", "--option", "o2,o4", "--promised", "380",
                "--out", str(out),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["可签发"])
            # 新资料可直接用于后续轮次报价
            follow = run_cli("service", str(out), "--seq", "1", "--family", "h4")
            self.assertEqual(follow.returncode, 0, follow.stderr)
            payload = json.loads(follow.stdout)
            self.assertEqual(payload["已发保证"][0]["承诺"], 380)
            self.assertEqual(payload["已发保证"][0]["状态"], "待受理·可兑现")

    def test_issue_rejection_exit_code(self):
        result = run_cli(
            "issue", "data/samples.json", "--seq", "3",
            "--family", "h4", "--option", "o1,o6", "--promised", "260",
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["可签发"])


if __name__ == "__main__":
    unittest.main()
