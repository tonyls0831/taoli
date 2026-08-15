import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "scripts" / "README.md"

ROOT_RELATIVE_COMMANDS = (
    "`python scripts/typhoon_watch.py --fast`",
    "`python scripts/dividend_spread.py`",
    "`python scripts/settlement_monitor.py --stock 2603`",
    "`python scripts/morning_brief.py`",
    (
        "python scripts/typhoon_watch.py --once --source-file "
        "tests/fixtures/dgpa/taipei_normal.html"
    ),
    (
        "python scripts/dividend_spread.py --replay "
        "tests/fixtures/dividend_spread/happy_path"
    ),
    (
        "python scripts/settlement_monitor.py --replay "
        "tests/fixtures/settlement_monitor/happy_path"
    ),
    (
        "python scripts/morning_brief.py --replay "
        "tests/fixtures/morning_brief/happy_path"
    ),
)


class ScriptsReadmeCommandTest(unittest.TestCase):
    def test_commands_are_explicitly_runnable_from_repository_root(self):
        text = README.read_text(encoding="utf-8")

        self.assertIn("以下命令均從 repository 根目錄執行", text)
        for command in ROOT_RELATIVE_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, text)


if __name__ == "__main__":
    unittest.main()
