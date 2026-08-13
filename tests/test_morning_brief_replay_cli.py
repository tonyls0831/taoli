import os
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from tests.replay_safety import file_snapshot, recording_proxy


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "morning_brief.py"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "morning_brief"
HAPPY_PATH = FIXTURE_ROOT / "happy_path"
CONFIG = ROOT / "scripts" / "config.json"
BRIEF_DIR = ROOT / "盤前簡報"


@contextmanager
def copied_replay_case(source: Path = HAPPY_PATH):
    with tempfile.TemporaryDirectory() as temp_dir:
        case_dir = Path(temp_dir) / source.name
        shutil.copytree(source, case_dir)
        yield case_dir


def run_replay(
    case_dir: Path,
    output_dir: Path,
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
        [
            sys.executable,
            str(SCRIPT),
            "--replay",
            str(case_dir),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )


class MorningBriefReplayCliTest(unittest.TestCase):
    def test_replay_writes_known_brief_to_explicit_safe_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "briefs"
            result = run_replay(HAPPY_PATH, output_dir)
            report_path = output_dir / "2026-07-01.md"
            report = (
                report_path.read_text(encoding="utf-8")
                if report_path.exists()
                else ""
            )

        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        observed = {
            "returncode": result.returncode,
            "fixed_time": "離線重播 2026-07-01 07:10:00" in stdout,
            "console_human_boundary": (
                "僅供盤前研究與人工核對，不是下單或交易授權" in stdout
            ),
            "report_written": report.startswith("# 盤前簡報 2026-07-01（三）"),
            "known_yahoo_move": "台積電ADR：184.50（+2.50%）" in report,
            "known_night_session": "2026/06/30 夜盤 202607：收 22500" in report,
            "known_dividend": (
                "| 2330 | 台積電 | 20.00 | 100.0 | 80.00 | 20.0% | ⭐觀察 |"
                in report
            ),
            "known_institutional": "台積電(+5,000)" in report,
            "fixed_generated_at": "產生時間：2026-07-01 07:10:00" in report,
            "human_boundary": (
                "僅供盤前研究與人工核對，不是下單或交易授權" in report
            ),
        }
        expected = {
            "returncode": 0,
            "fixed_time": True,
            "console_human_boundary": True,
            "report_written": True,
            "known_yahoo_move": True,
            "known_night_session": True,
            "known_dividend": True,
            "known_institutional": True,
            "fixed_generated_at": True,
            "human_boundary": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_replay_names_each_invalid_provider_without_writing_report(self):
        invalid_sources = {
            "missing_taifex": (
                "taifex_night.csv",
                None,
                "taifex_night",
            ),
            "invalid_taifex": (
                "taifex_night.csv",
                b"malformed\n",
                "taifex_night",
            ),
            "nonfinite_taifex": (
                "taifex_night.csv",
                (HAPPY_PATH / "taifex_night.csv")
                .read_bytes()
                .replace(b"22500", b"NaN"),
                "taifex_night",
            ),
            "invalid_dividends": (
                "twse_dividends.json",
                b"{}\n",
                "twse_dividends",
            ),
            "invalid_dividend_date": (
                "twse_dividends.json",
                json.dumps(
                    [
                        {
                            "Date": {"unexpected": True},
                            "Code": "2330",
                            "Name": "台積電",
                            "CashDividend": "20",
                        }
                    ],
                    ensure_ascii=False,
                ).encode("utf-8"),
                "twse_dividends",
            ),
            "invalid_closes": (
                "twse_closes.json",
                b"{}\n",
                "twse_closes",
            ),
            "nonfinite_closes": (
                "twse_closes.json",
                json.dumps(
                    [{"Code": "2330", "ClosingPrice": "NaN"}]
                ).encode("utf-8"),
                "twse_closes",
            ),
            "invalid_t86": (
                "twse_t86.json",
                b"{}\n",
                "twse_t86",
            ),
        }

        for case_name, (filename, replacement, source_name) in invalid_sources.items():
            with (
                self.subTest(case=case_name),
                copied_replay_case() as case_dir,
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                source_path = case_dir / filename
                if replacement is None:
                    source_path.unlink()
                else:
                    source_path.write_bytes(replacement)
                output_dir = Path(temp_dir) / "briefs"
                result = run_replay(case_dir, output_dir)
                report_exists = (output_dir / "2026-07-01.md").exists()

            stderr = result.stderr.decode("utf-8", errors="replace")
            observed = {
                "returncode": result.returncode,
                "source_named": source_name in stderr,
                "traceback_hidden": "Traceback" not in stderr,
                "report_absent": not report_exists,
            }
            expected = {
                "returncode": 1,
                "source_named": True,
                "traceback_hidden": True,
                "report_absent": True,
            }

            self.assertEqual(observed, expected, stderr)

    def test_replay_rejects_output_io_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            blocking_file = Path(temp_dir) / "not-a-directory"
            blocking_file.write_text("occupied", encoding="utf-8")
            result = run_replay(HAPPY_PATH, blocking_file / "briefs")

        stderr = result.stderr.decode("utf-8", errors="replace")
        observed = {
            "returncode": result.returncode,
            "output_error": "replay scenario 無效" in stderr,
            "traceback_hidden": "Traceback" not in stderr,
        }
        expected = {
            "returncode": 2,
            "output_error": True,
            "traceback_hidden": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_replay_ignores_unrelated_stock_without_positive_close(self):
        with (
            copied_replay_case() as case_dir,
            tempfile.TemporaryDirectory() as temp_dir,
        ):
            closes_path = case_dir / "twse_closes.json"
            closes = json.loads(closes_path.read_text(encoding="utf-8"))
            closes.append({"Code": "9999", "ClosingPrice": "0"})
            closes_path.write_text(
                json.dumps(closes, ensure_ascii=False), encoding="utf-8"
            )
            output_dir = Path(temp_dir) / "briefs"
            result = run_replay(case_dir, output_dir)
            report_exists = (output_dir / "2026-07-01.md").exists()

        stderr = result.stderr.decode("utf-8", errors="replace")
        observed = {
            "returncode": result.returncode,
            "report_written": report_exists,
        }
        expected = {
            "returncode": 0,
            "report_written": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_replay_fails_clearly_when_yahoo_tsm_has_insufficient_closes(self):
        with copied_replay_case() as case_dir, tempfile.TemporaryDirectory() as temp_dir:
            (case_dir / "yahoo_tsm.json").write_text(
                json.dumps(
                    {
                        "chart": {
                            "result": [
                                {
                                    "indicators": {
                                        "quote": [{"close": [184.5]}]
                                    }
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            output_dir = Path(temp_dir) / "briefs"
            result = run_replay(case_dir, output_dir)
            report_exists = (output_dir / "2026-07-01.md").exists()

        stderr = result.stderr.decode("utf-8", errors="replace")
        observed = {
            "returncode": result.returncode,
            "source_named": "yahoo[TSM]" in stderr,
            "invalid_data_reported": "沒有兩筆有效收盤價" in stderr,
            "traceback_hidden": "Traceback" not in stderr,
            "report_absent": not report_exists,
        }
        expected = {
            "returncode": 1,
            "source_named": True,
            "invalid_data_reported": True,
            "traceback_hidden": True,
            "report_absent": True,
        }

        self.assertEqual(observed, expected, stderr)


class MorningBriefReplaySafetyTest(unittest.TestCase):
    def test_replays_avoid_network_notification_config_and_historical_reports(self):
        config_before = file_snapshot(CONFIG)
        reports_before = {
            path.relative_to(BRIEF_DIR): path.read_bytes()
            for path in BRIEF_DIR.rglob("*")
            if path.is_file()
        }

        with (
            copied_replay_case() as invalid_case,
            tempfile.TemporaryDirectory() as temp_dir,
            recording_proxy() as proxy,
        ):
            (invalid_case / "yahoo_tsm.json").write_text(
                json.dumps(
                    {
                        "chart": {
                            "result": [
                                {"indicators": {"quote": [{"close": [184.5]}]}}
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            sentinel_path = Path(temp_dir) / "sentinel"
            sentinel_path.mkdir()
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
                "PYTHONPATH": os.pathsep.join(
                    filter(
                        None,
                        (str(sentinel_path), os.environ.get("PYTHONPATH")),
                    )
                ),
            }
            happy_output = Path(temp_dir) / "happy"
            invalid_output = Path(temp_dir) / "invalid"
            results = [
                run_replay(
                    HAPPY_PATH,
                    happy_output,
                    env_overrides=env_overrides,
                ),
                run_replay(
                    invalid_case,
                    invalid_output,
                    env_overrides=env_overrides,
                ),
                run_replay(
                    HAPPY_PATH,
                    BRIEF_DIR,
                    env_overrides=env_overrides,
                ),
                run_replay(
                    HAPPY_PATH,
                    ROOT / "data" / "replay-output",
                    env_overrides=env_overrides,
                ),
            ]
            beep_called = (sentinel_path / "beep_called").exists()
            safe_output_files = [
                path.relative_to(Path(temp_dir))
                for path in Path(temp_dir).rglob("*.md")
            ]

        reports_after = {
            path.relative_to(BRIEF_DIR): path.read_bytes()
            for path in BRIEF_DIR.rglob("*")
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
            "historical_reports_unchanged": reports_after == reports_before,
            "only_happy_output_written": safe_output_files == [
                Path("happy") / "2026-07-01.md"
            ],
        }
        expected = {
            "returncodes": [0, 1, 2, 2],
            "network_connections": 0,
            "beep_called": False,
            "config_unchanged": True,
            "historical_reports_unchanged": True,
            "only_happy_output_written": True,
        }

        self.assertEqual(observed, expected, stderr)
if __name__ == "__main__":
    unittest.main()
