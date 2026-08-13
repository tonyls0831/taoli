import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from tests.replay_safety import file_snapshot, recording_proxy


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dividend_spread.py"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "dividend_spread"
HAPPY_PATH = FIXTURE_ROOT / "happy_path"
INVALID_COMPANY_SHARES = FIXTURE_ROOT / "invalid_company_shares"
CONFIG = ROOT / "scripts" / "config.json"
STATE_FILE = ROOT / "data" / "dividend_spread_state.json"
DATA_DIR = ROOT / "data"


@contextmanager
def copied_replay_case(source: Path = HAPPY_PATH):
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = Path(temp_dir) / source.name
        shutil.copytree(source, case_dir)
        yield case_dir


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


class DividendSpreadReplayCliTest(unittest.TestCase):
    def test_replay_reports_worked_example_and_manual_verification_alert(self):
        result = run_replay(HAPPY_PATH)
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        observed = {
            "returncode": result.returncode,
            "fixed_date": "離線重播 2026-07-01" in stdout,
            "near_bucket": "D_near**（今天→近月結算的蒸發點數）：**100.0 點**" in stdout,
            "cross_bucket": "D_cross**（近月→次月結算的蒸發點數）：**100.0 點**" in stdout,
            "reasonable_spread": "= -105.0 點" in stdout,
            "market_spread": "19,890 − 20,000 = **-110.0 點**" in stdout,
            "fixed_jump": "合理價差變動 **-20.0 點**" in stdout,
            "manual_verification": "請人工核對除息資料" in stdout,
            "not_execution_authority": "不代表任何部位條件已成立" in stdout,
        }
        expected = {
            "returncode": 0,
            "fixed_date": True,
            "near_bucket": True,
            "cross_bucket": True,
            "reasonable_spread": True,
            "market_spread": True,
            "fixed_jump": True,
            "manual_verification": True,
            "not_execution_authority": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_replay_fails_clearly_when_company_shares_has_no_valid_rows(self):
        result = run_replay(INVALID_COMPANY_SHARES)
        stderr = result.stderr.decode("utf-8", errors="replace")

        observed = {
            "nonzero_exit": result.returncode != 0,
            "source_named": "twse_company_shares" in stderr,
            "invalid_data_reported": "沒有有效公司股數資料" in stderr,
        }
        expected = {
            "nonzero_exit": True,
            "source_named": True,
            "invalid_data_reported": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_replay_fails_clearly_when_closing_prices_has_no_valid_rows(self):
        with copied_replay_case() as case_dir:
            (case_dir / "twse_closing_prices.json").write_text(
                "[]\n", encoding="utf-8"
            )
            result = run_replay(case_dir)

        stderr = result.stderr.decode("utf-8", errors="replace")
        observed = {
            "nonzero_exit": result.returncode != 0,
            "source_named": "twse_closing_prices" in stderr,
            "invalid_data_reported": "沒有有效收盤價資料" in stderr,
        }
        expected = {
            "nonzero_exit": True,
            "source_named": True,
            "invalid_data_reported": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_replay_rejects_invalid_closing_price_field_without_traceback(self):
        with copied_replay_case() as case_dir:
            (case_dir / "twse_closing_prices.json").write_text(
                json.dumps([
                    {"Code": "2330", "ClosingPrice": {"unexpected": 1}}
                ]),
                encoding="utf-8",
            )
            result = run_replay(case_dir)

        stderr = result.stderr.decode("utf-8", errors="replace")
        observed = {
            "nonzero_exit": result.returncode != 0,
            "source_named": "twse_closing_prices" in stderr,
            "traceback_hidden": "Traceback" not in stderr,
        }
        expected = {
            "nonzero_exit": True,
            "source_named": True,
            "traceback_hidden": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_replay_warns_and_degrades_when_taifex_rows_are_invalid(self):
        with copied_replay_case() as case_dir:
            (case_dir / "taifex_futures.csv").write_text(
                "malformed\n", encoding="big5"
            )
            result = run_replay(case_dir)

        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        observed = {
            "returncode": result.returncode,
            "warning": "[warn] TAIFEX 價差抓取失敗" in stdout,
            "source_named": "taifex_futures" in stdout,
            "market_spread_omitted": "市場價差（" not in stdout,
        }
        expected = {
            "returncode": 0,
            "warning": True,
            "source_named": True,
            "market_spread_omitted": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_replay_rejects_invalid_scenario_shapes_without_traceback(self):
        valid_scenario = json.loads(
            (HAPPY_PATH / "scenario.json").read_text(encoding="utf-8")
        )
        invalid_cases = {
            "top_level_array": [],
            "nonnumeric_previous_fair": {
                **valid_scenario,
                "previous_state": {
                    **valid_scenario["previous_state"],
                    "fair": "not-a-number",
                },
            },
        }

        for case_name, scenario in invalid_cases.items():
            with self.subTest(case=case_name), copied_replay_case() as case_dir:
                (case_dir / "scenario.json").write_text(
                    json.dumps(scenario, ensure_ascii=False), encoding="utf-8"
                )
                result = run_replay(case_dir)

            stderr = result.stderr.decode("utf-8", errors="replace")
            observed = {
                "returncode": result.returncode,
                "scenario_error": "[error] replay scenario 無效" in stderr,
                "traceback_hidden": "Traceback" not in stderr,
            }
            expected = {
                "returncode": 2,
                "scenario_error": True,
                "traceback_hidden": True,
            }

            self.assertEqual(observed, expected, stderr)

    def test_replay_names_invalid_required_twse_payloads(self):
        invalid_sources = {
            "twse_index.json": {
                "payload": {"msgArray": []},
                "source": "twse_index",
                "message": "沒有有效加權指數資料",
            },
            "twse_dividend_events.json": {
                "payload": [[]],
                "source": "twse_dividend_events",
                "message": "除息事件列必須是物件",
            },
        }

        for filename, expected_error in invalid_sources.items():
            with self.subTest(
                source=expected_error["source"]
            ), copied_replay_case() as case_dir:
                (case_dir / filename).write_text(
                    json.dumps(expected_error["payload"], ensure_ascii=False),
                    encoding="utf-8",
                )
                result = run_replay(case_dir)

            stderr = result.stderr.decode("utf-8", errors="replace")
            observed = {
                "nonzero_exit": result.returncode != 0,
                "source_named": expected_error["source"] in stderr,
                "reason_named": expected_error["message"] in stderr,
                "traceback_hidden": "Traceback" not in stderr,
            }
            expected = {
                "nonzero_exit": True,
                "source_named": True,
                "reason_named": True,
                "traceback_hidden": True,
            }

            self.assertEqual(observed, expected, stderr)


class DividendSpreadReplaySafetyTest(unittest.TestCase):
    def test_replays_avoid_network_notification_and_runtime_files(self):
        config_before = file_snapshot(CONFIG)
        state_before = file_snapshot(STATE_FILE)
        reports_before = {
            path: path.read_bytes() for path in DATA_DIR.glob("除權息價差_*.md")
        }

        with copied_replay_case() as invalid_taifex_case:
            (invalid_taifex_case / "taifex_futures.csv").write_text(
                "malformed\n", encoding="big5"
            )
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
                    for case_dir in (
                        HAPPY_PATH,
                        INVALID_COMPANY_SHARES,
                        invalid_taifex_case,
                    )
                ]
                beep_called = (sentinel_path / "beep_called").exists()

        reports_after = {
            path: path.read_bytes() for path in DATA_DIR.glob("除權息價差_*.md")
        }
        stderr = b"\n".join(result.stderr for result in results).decode(
            "utf-8", errors="replace"
        )
        observed = {
            "returncodes": [result.returncode for result in results],
            "network_connections": proxy.connection_count,
            "beep_called": beep_called,
            "config_unchanged": file_snapshot(CONFIG) == config_before,
            "state_unchanged": file_snapshot(STATE_FILE) == state_before,
            "reports_unchanged": reports_after == reports_before,
        }
        expected = {
            "returncodes": [0, 1, 0],
            "network_connections": 0,
            "beep_called": False,
            "config_unchanged": True,
            "state_unchanged": True,
            "reports_unchanged": True,
        }

        self.assertEqual(observed, expected, stderr)

if __name__ == "__main__":
    unittest.main()
