import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class ConsoleEncodingRegressionTest(unittest.TestCase):
    def test_typhoon_context_prints_when_parent_console_is_cp950(self):
        code = (
            "import sys; "
            "from datetime import datetime; "
            "from zoneinfo import ZoneInfo; "
            f"sys.path.insert(0, {str(SCRIPTS)!r}); "
            "import typhoon_watch as watcher; "
            "watcher.now_taipei = lambda: datetime("
            "2026, 8, 11, 12, 0, tzinfo=ZoneInfo('Asia/Taipei')); "
            "print(watcher.settlement_context())"
        )
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp950"

        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            result.stderr.decode("cp950", errors="replace"),
        )
        self.assertIn("⚡".encode("utf-8"), result.stdout)


if __name__ == "__main__":
    unittest.main()
