import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "typhoon_watch.py"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "dgpa"
NORMAL_FIXTURE = FIXTURE_DIR / "taipei_normal.html"
SUSPENSION_FIXTURE = FIXTURE_DIR / "taipei_suspension.html"
MISSING_TAIPEI_FIXTURE = FIXTURE_DIR / "missing_taipei.html"
CONFIG = ROOT / "scripts" / "config.json"
DATA_DIR = ROOT / "data"


def file_snapshot(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def run_fixture_cli(
    fixture: Path = NORMAL_FIXTURE,
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
            "--once",
            "--source-file",
            str(fixture),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )


class RecordingProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.connection_count += 1
        self.request.recv(1024)
        self.request.sendall(b"HTTP/1.1 502 Offline Replay\r\nContent-Length: 0\r\n\r\n")


@contextmanager
def recording_proxy():
    with socketserver.TCPServer(("127.0.0.1", 0), RecordingProxyHandler) as server:
        server.connection_count = 0
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


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

    def test_once_replays_suspension_as_manual_verification_alert(self):
        result = run_fixture_cli(SUSPENSION_FIXTURE)
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        observed = {
            "returncode": result.returncode,
            "suspension_reported": "臺北市：明日停止上班、停止上課" in stdout,
            "manual_verification_required": (
                "人工核對" in stdout and "DGPA" in stdout and "交易所" in stdout
            ),
            "trade_command_rejected": "不代表任何交易或下單指示" in stdout,
            "beep_suppressed": "\a" not in stdout,
        }
        expected = {
            "returncode": 0,
            "suspension_reported": True,
            "manual_verification_required": True,
            "trade_command_rejected": True,
            "beep_suppressed": True,
        }

        self.assertEqual(observed, expected, stderr)

    def test_once_replays_missing_taipei_as_clear_degradation(self):
        result = run_fixture_cli(MISSING_TAIPEI_FIXTURE)
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        observed = {
            "returncode": result.returncode,
            "missing_data_reported": "頁面目前無臺北市列" in stdout,
            "alert_suppressed": "事件警報" not in stdout,
        }
        expected = {
            "returncode": 0,
            "missing_data_reported": True,
            "alert_suppressed": True,
        }

        self.assertEqual(observed, expected, stderr)


class TyphoonFixtureSafetyTest(unittest.TestCase):
    def test_all_fixture_replays_avoid_external_and_filesystem_side_effects(self):
        config_before = file_snapshot(CONFIG)
        runtime_state_before = {
            path: path.read_bytes() for path in DATA_DIR.glob("*_state.json")
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
                "PYTHONPATH": os.pathsep.join(
                    filter(None, (str(sentinel_path), os.environ.get("PYTHONPATH")))
                ),
            }
            results = [
                run_fixture_cli(fixture, env_overrides=env_overrides)
                for fixture in (
                    NORMAL_FIXTURE,
                    SUSPENSION_FIXTURE,
                    MISSING_TAIPEI_FIXTURE,
                )
            ]
            beep_called = (sentinel_path / "beep_called").exists()

        runtime_state_after = {
            path: path.read_bytes() for path in DATA_DIR.glob("*_state.json")
        }
        stderr = b"\n".join(result.stderr for result in results).decode(
            "utf-8", errors="replace"
        )

        observed = {
            "returncodes": [result.returncode for result in results],
            "network_connections": proxy.connection_count,
            "beep_called": beep_called,
            "config_unchanged": file_snapshot(CONFIG) == config_before,
            "runtime_state_unchanged": runtime_state_after == runtime_state_before,
        }
        expected = {
            "returncodes": [0, 0, 0],
            "network_connections": 0,
            "beep_called": False,
            "config_unchanged": True,
            "runtime_state_unchanged": True,
        }

        self.assertEqual(observed, expected, stderr)


if __name__ == "__main__":
    unittest.main()
