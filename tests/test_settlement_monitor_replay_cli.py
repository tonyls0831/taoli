import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.replay_safety import file_snapshot, recording_proxy


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "settlement_monitor.py"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "settlement_monitor"
HAPPY_PATH = FIXTURE_ROOT / "happy_path"
INVALID_SPOT = FIXTURE_ROOT / "invalid_spot"
INVALID_FUTURES = FIXTURE_ROOT / "invalid_futures"
CONFIG = ROOT / "scripts" / "config.json"
DATA_DIR = ROOT / "data"


def run_replay(
    case_dir: Path,
    *,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(
        {
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
    )
    env.update(env_overrides or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--replay", str(case_dir)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )


class SettlementMonitorReplayCliTest(unittest.TestCase):
    def test_replay_reports_known_model_interval_and_human_boundary(self):
        result = run_replay(HAPPY_PATH)
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        observed = {
            "returncode": result.returncode,
            "fixed_date": "離線重播 2026-08-19" in stdout,
            "complete_sequence": "n=661/661" in stdout,
            "known_mean": "最終估計均值 100.0000（樣本 661 筆）" in stdout,
            "model_alert": "SOP-3 結算價模型區間縮窄" in stdout,
            "official_value_separate": "正式結算價以期交所公告為準" in stdout,
            "human_decision": "請人工核對樣本完整性" in stdout,
            "not_trade_authority": "不代表下單建議" in stdout,
        }
        expected = {
            "returncode": 0,
            "fixed_date": True,
            "complete_sequence": True,
            "known_mean": True,
            "model_alert": True,
            "official_value_separate": True,
            "human_decision": True,
            "not_trade_authority": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_replay_fails_clearly_when_twse_spot_has_no_quote(self):
        result = run_replay(INVALID_SPOT)
        stderr = result.stderr.decode("utf-8", errors="replace")

        observed = {
            "nonzero_exit": result.returncode != 0,
            "source_named": "twse_spot" in stderr,
            "invalid_data_reported": "沒有有效報價" in stderr,
            "traceback_hidden": "Traceback" not in stderr,
        }
        expected = {
            "nonzero_exit": True,
            "source_named": True,
            "invalid_data_reported": True,
            "traceback_hidden": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_replay_warns_and_degrades_when_taifex_quote_is_invalid(self):
        result = run_replay(INVALID_FUTURES)
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        observed = {
            "returncode": result.returncode,
            "source_warning": (
                "[warn] 期貨報價抓取失敗" in stdout
                and "taifex_futures" in stdout
            ),
            "sequence_completed": "最終估計均值 100.0000（樣本 661 筆）" in stdout,
        }
        expected = {
            "returncode": 0,
            "source_warning": True,
            "sequence_completed": True,
        }

        self.assertEqual(observed, expected, stderr)


class SettlementMonitorReplaySafetyTest(unittest.TestCase):
    def test_replays_avoid_network_notification_and_runtime_files(self):
        config_before = file_snapshot(CONFIG)
        data_before = {
            path.relative_to(DATA_DIR): path.read_bytes()
            for path in DATA_DIR.rglob("*")
            if path.is_file()
        }

        with tempfile.TemporaryDirectory() as sentinel_dir, recording_proxy() as proxy:
            sentinel_path = Path(sentinel_dir)
            (sentinel_path / "winsound.py").write_text(
                "from pathlib import Path\n"
                "def Beep(frequency, duration):\n"
                "    Path(__file__).with_name('beep_called').touch()\n",
                encoding="utf-8",
            )
            proxy_url = f"http://127.0.0.1:{proxy.server_address[1]}"
            env_overrides = {
                "HTTP_PROXY": proxy_url,
                "HTTPS_PROXY": proxy_url,
                "PYTHONPATH": os.pathsep.join(filter(None, (
                    str(sentinel_path),
                    os.environ.get("PYTHONPATH"),
                ))),
            }
            results = [
                run_replay(case_dir, env_overrides=env_overrides)
                for case_dir in (HAPPY_PATH, INVALID_SPOT, INVALID_FUTURES)
            ]
            beep_called = (sentinel_path / "beep_called").exists()

        data_after = {
            path.relative_to(DATA_DIR): path.read_bytes()
            for path in DATA_DIR.rglob("*")
            if path.is_file()
        }
        stderr = b"\n".join(result.stderr for result in results).decode(
            "utf-8", errors="replace"
        )
        observed = {
            "returncodes": [result.returncode for result in results],
            "network_connections": proxy.connection_count,
            "beep_called": beep_called,
            "config_unchanged": file_snapshot(CONFIG) == config_before,
            "data_unchanged": data_after == data_before,
        }
        expected = {
            "returncodes": [0, 1, 0],
            "network_connections": 0,
            "beep_called": False,
            "config_unchanged": True,
            "data_unchanged": True,
        }

        self.assertEqual(observed, expected, stderr)
if __name__ == "__main__":
    unittest.main()
