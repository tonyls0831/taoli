import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPERATIONAL_FILES = [*sorted((ROOT / "scripts").glob("*.py")), ROOT / "scripts" / "README.md"]
FORBIDDEN_PHRASES = (
    "立即執行",
    "進場訊號",
    "市價雙買",
    "掃單",
    "穩賺",
    "按 SOP-2 建倉",
    "空現貨＋買期貨",
    "買現貨＋空期貨",
    "收斂 <0.5 元雙平",
)


class AlertLanguageGuardTest(unittest.TestCase):
    def test_operational_alerts_do_not_contain_trade_commands(self):
        for path in OPERATIONAL_FILES:
            text = path.read_text(encoding="utf-8")
            for phrase in FORBIDDEN_PHRASES:
                with self.subTest(path=path.name, phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_typhoon_alert_requires_manual_verification(self):
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        import typhoon_watch

        message = typhoon_watch.build_alert_message("臺北市：停止上班、停止上課")
        self.assertIn("人工核對", message)
        self.assertIn("不代表任何交易或下單指示", message)


if __name__ == "__main__":
    unittest.main()
