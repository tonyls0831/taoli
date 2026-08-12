import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "typhoon_watch.py"
FIXTURE = ROOT / "tests" / "fixtures" / "dgpa" / "taipei_normal.html"
CONFIG = ROOT / "scripts" / "config.json"


def file_snapshot(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def run_fixture_cli() -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(
        {
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
    )

    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--once",
            "--source-file",
            str(FIXTURE),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )


class TyphoonFixtureCliTest(unittest.TestCase):
    def test_once_replays_normal_status_without_network_notifications(self):
        result = run_fixture_cli()
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        observed = {
            "returncode": result.returncode,
            "offline_source_reported": "離線來源" in stdout,
            "normal_status_reported": (
                "無停班訊息 | 臺北市: 今日照常上班、照常上課" in stdout
            ),
            "alert_suppressed": "事件警報" not in stdout,
        }
        expected = {
            "returncode": 0,
            "offline_source_reported": True,
            "normal_status_reported": True,
            "alert_suppressed": True,
        }

        self.assertEqual(observed, expected, stderr)


class TyphoonFixtureSafetyTest(unittest.TestCase):
    def test_fixture_replay_preserves_local_config(self):
        config_before = file_snapshot(CONFIG)

        result = run_fixture_cli()
        stderr = result.stderr.decode("utf-8", errors="replace")

        observed = {
            "returncode": result.returncode,
            "config_unchanged": file_snapshot(CONFIG) == config_before,
        }
        expected = {
            "returncode": 0,
            "config_unchanged": True,
        }

        self.assertEqual(observed, expected, stderr)


if __name__ == "__main__":
    unittest.main()
