# -*- coding: utf-8 -*-
"""SOP-3/4 結算日監控器：即時結算均價 + 鎖定區間 +（可選）期現價差。

原理：股票期貨結算價 = 結算日 12:30（不含）–13:25 現貨每 5 秒快照（660 個）
＋ 13:30 收盤價，共 661 個數字的算術平均。
本腳本每 5 秒抓一次現貨即時價，維護：
  - 目前累計均值 M
  - 鎖定區間 [worst_low, worst_high]：剩餘樣本全走跌停/漲停時最終均值的極限
區間寬 < 1 tick 時（實務 13:10 後）= 結算價已可 100% 確定 → 警報並提示可掛的內側價位。

SOP-4：加 --futures-symbol（TAIFEX MIS 代號，例 CDFH6-F）即同步抓股期報價，
期現價差 > 門檻（%）時警報。

用法：
  python settlement_monitor.py --stock 2603              # 結算日 12:25 前開著
  python settlement_monitor.py --stock 2603 --force      # 非結算日/盤後測試
  python settlement_monitor.py --stock 2603 --futures-symbol DBFH6-F
"""
import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from common import (TZ, load_config, make_session, notify, now_taipei,
                    third_wednesday)

MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
TAIFEX_MIS = "https://mis.taifex.com.tw/futures/api/getQuoteDetail"
TOTAL_SAMPLES = 661          # 660 個 5 秒快照 + 收盤價
SAMPLE_LATE_TOLERANCE_SECONDS = 1


class ReplayScenarioError(Exception):
    """離線重播 scenario 不符合公開 Interface。"""


class ReplaySourceError(Exception):
    """離線重播的外部資料 fixture 無法使用。"""


class ReplayResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class ReplaySession:
    """以 fixture 時序取代必要的 TWSE MIS 邊界與時間進程。"""

    def __init__(
        self,
        payloads: list[dict],
        start: datetime,
        step_seconds: int,
        futures_payloads: list[dict] | None = None,
    ):
        self.payloads = payloads
        self.start = start
        self.step_seconds = step_seconds
        self.cursor = 0
        self.current_time = start
        self.futures_payloads = futures_payloads or []
        self.futures_cursor = 0

    def get(self, url, **_kwargs):
        if url != MIS_URL:
            raise ReplaySourceError(f"不支援的 replay GET 來源: {url}")
        if self.cursor >= len(self.payloads):
            raise ReplaySourceError("twse_spot: fixture 樣本已用完")
        if self.cursor == len(self.payloads) - 1:
            self.current_time = self.start.replace(
                hour=13, minute=30, second=0, microsecond=0
            )
        else:
            sample_index = max(self.cursor - 1, 0)
            self.current_time = self.start + timedelta(
                seconds=sample_index * self.step_seconds
            )
        payload = self.payloads[self.cursor]
        self.cursor += 1
        return ReplayResponse(payload)

    def post(self, url, **_kwargs):
        if url != TAIFEX_MIS:
            raise ReplaySourceError(f"不支援的 replay POST 來源: {url}")
        if self.futures_cursor >= len(self.futures_payloads):
            raise ReplaySourceError("taifex_futures: fixture 樣本已用完")
        payload = self.futures_payloads[self.futures_cursor]
        self.futures_cursor += 1
        return ReplayResponse(payload)

    def now(self) -> datetime:
        return self.current_time


def replay_source_path(
    case_dir: Path, source_name: str, relative_path: str
) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ReplayScenarioError(
            f"sources.{source_name} 必須是相對檔案路徑"
        )
    resolved_case = case_dir.resolve()
    resolved_path = (case_dir / relative_path).resolve()
    try:
        resolved_path.relative_to(resolved_case)
    except ValueError as e:
        raise ReplayScenarioError(
            f"{source_name}: 來源路徑不可離開 case directory"
        ) from e
    return resolved_path


def expand_replay_runs(fixture: dict, source_name: str) -> list[dict]:
    if not isinstance(fixture, dict) or not isinstance(fixture.get("runs"), list):
        raise ReplaySourceError(f"{source_name}: runs 必須是陣列")
    payloads = []
    for run in fixture["runs"]:
        if not isinstance(run, dict):
            raise ReplaySourceError(f"{source_name}: run 必須是物件")
        repeat = run.get("repeat")
        payload = run.get("payload")
        if (
            isinstance(repeat, bool)
            or not isinstance(repeat, int)
            or repeat < 1
        ):
            raise ReplaySourceError(f"{source_name}: repeat 必須是正整數")
        if not isinstance(payload, dict):
            raise ReplaySourceError(f"{source_name}: payload 必須是物件")
        payloads.extend([payload] * repeat)
    return payloads


def load_replay_case(case_dir: Path) -> dict:
    if not case_dir.is_dir():
        raise ReplayScenarioError(f"找不到 case directory: {case_dir}")
    scenario_path = case_dir / "scenario.json"
    try:
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ReplayScenarioError("找不到 scenario.json") from e
    except (UnicodeError, json.JSONDecodeError) as e:
        raise ReplayScenarioError(
            f"scenario.json 無效 ({type(e).__name__})"
        ) from e

    if not isinstance(scenario, dict):
        raise ReplayScenarioError("scenario.json 頂層必須是物件")
    if scenario.get("schema_version") != 1:
        raise ReplayScenarioError("schema_version 必須是 1")
    try:
        as_of_date = date.fromisoformat(scenario["as_of_date"])
    except (KeyError, TypeError, ValueError) as e:
        raise ReplayScenarioError("as_of_date 必須是 YYYY-MM-DD") from e
    stock = scenario.get("stock")
    if not isinstance(stock, str) or not stock:
        raise ReplayScenarioError("stock 必須是非空字串")
    model = scenario.get("model")
    if not isinstance(model, dict):
        raise ReplayScenarioError("model 必須是物件")
    try:
        basis_alert_pct = float(model["basis_alert_pct"])
    except (KeyError, TypeError, ValueError) as e:
        raise ReplayScenarioError("model.basis_alert_pct 必須是數字") from e
    sources = scenario.get("sources")
    if not isinstance(sources, dict):
        raise ReplayScenarioError("sources 必須是物件")
    source_path = replay_source_path(
        case_dir, "twse_spot", sources.get("twse_spot")
    )
    try:
        fixture = json.loads(source_path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ReplaySourceError(
            f"twse_spot: 來源檔案無法讀取 ({type(e).__name__})"
        ) from e
    except (UnicodeError, json.JSONDecodeError) as e:
        raise ReplaySourceError(
            f"twse_spot: 來源檔案無效 ({type(e).__name__})"
        ) from e

    try:
        start = datetime.fromisoformat(fixture["start"])
        step_seconds = int(fixture["step_seconds"])
        payloads = expand_replay_runs(fixture, "twse_spot")
    except (KeyError, TypeError, ValueError) as e:
        raise ReplaySourceError("twse_spot: fixture 時序格式無效") from e
    if step_seconds != 5:
        raise ReplaySourceError("twse_spot: step_seconds 必須是 5")
    if start.date() != as_of_date:
        raise ReplaySourceError("twse_spot: start 日期與 as_of_date 不一致")
    if (start.hour, start.minute, start.second, start.microsecond) != (
        12, 30, 5, 0
    ):
        raise ReplaySourceError("twse_spot: start 必須是 12:30:05")
    if len(payloads) != TOTAL_SAMPLES + 1:
        raise ReplaySourceError(
            f"twse_spot: 必須提供初始報價與 {TOTAL_SAMPLES} 筆樣本"
        )

    futures_symbol = scenario.get("futures_symbol", "")
    if not isinstance(futures_symbol, str):
        raise ReplayScenarioError("futures_symbol 必須是字串")
    futures_payloads = []
    futures_warning = None
    if futures_symbol:
        try:
            futures_path = replay_source_path(
                case_dir,
                "taifex_futures",
                sources.get("taifex_futures"),
            )
            try:
                futures_fixture = json.loads(
                    futures_path.read_text(encoding="utf-8")
                )
            except OSError as e:
                raise ReplaySourceError(
                    "taifex_futures: 來源檔案無法讀取 "
                    f"({type(e).__name__})"
                ) from e
            except (UnicodeError, json.JSONDecodeError) as e:
                raise ReplaySourceError(
                    "taifex_futures: fixture 格式無效"
                ) from e
            futures_payloads = expand_replay_runs(
                futures_fixture, "taifex_futures"
            )
        except (ReplayScenarioError, ReplaySourceError) as e:
            futures_warning = str(e)

    return {
        "as_of_date": as_of_date,
        "stock": stock,
        "futures_symbol": futures_symbol,
        "futures_warning": futures_warning,
        "config": {"basis_alert_pct": basis_alert_pct},
        "session": ReplaySession(
            payloads, start, step_seconds, futures_payloads
        ),
    }


def tick_size(price: float) -> float:
    for bound, tick in ((10, 0.01), (50, 0.05), (100, 0.1), (500, 0.5), (2500, 1)):
        if price < bound:
            return tick
    return 5.0


def fetch_spot(session, stock: str) -> dict:
    r = session.get(MIS_URL, params={"ex_ch": f"tse_{stock}.tw|otc_{stock}.tw",
                                     "json": "1", "delay": "0"}, timeout=10)
    r.raise_for_status()
    arr = r.json().get("msgArray", [])
    if not arr:
        raise RuntimeError(f"MIS 查不到 {stock}")
    q = arr[0]

    def num(key):
        try:
            return float(q.get(key, ""))
        except (TypeError, ValueError):
            return None

    return {"last": num("z"), "prev_close": num("y"),
            "limit_up": num("u"), "limit_dn": num("w"),
            "name": q.get("n", stock), "time": q.get("t", "")}


def fetch_futures(
    session, symbol: str, *, strict_source: bool = False
) -> float | None:
    try:
        r = session.post(TAIFEX_MIS, json={"SymbolID": symbol}, timeout=10)
        r.raise_for_status()
        d = r.json().get("RtData", {}).get("QuoteList", [])
        node = d[0] if d else r.json().get("RtData", {}).get("Quote", {})
        for k in ("CLastPrice", "CRefPrice", "LastPrice"):
            v = node.get(k)
            if v:
                return float(str(v).replace(",", ""))
        if strict_source:
            raise RuntimeError("taifex_futures: 沒有有效期貨報價")
    except Exception as e:
        print(f"[warn] 期貨報價抓取失敗: {e}")
    return None


def print_replay_alert(title: str, message: str):
    print(f"\n{'=' * 60}\n** {title} **\n{message}\n{'=' * 60}")


def emit_alert(
    title: str,
    message: str,
    cfg: dict,
    *,
    replay_mode: bool,
    sound: bool = True,
):
    if replay_mode:
        print_replay_alert(title, message)
    else:
        notify(title, message, cfg, sound=sound)


def run(args, replay: dict | None = None) -> int:
    replay_mode = replay is not None
    if replay:
        cfg = replay["config"]
        session = replay["session"]
        args.stock = replay["stock"]
        args.futures_symbol = replay["futures_symbol"]
        args.force = True
        args.max_iter = 0
        now = session.now
        sleep = lambda _seconds: None
        print(f"[settlement_monitor] 離線重播 {replay['as_of_date']}")
        if replay["futures_warning"]:
            print(
                "[warn] 期貨 replay 來源無效: "
                f"{replay['futures_warning']}；已停用選用期貨路徑"
            )
    else:
        cfg = load_config()
        session = make_session()
        now = now_taipei
        sleep = time.sleep

    today = now().date()

    settle = third_wednesday(today.year, today.month)
    if today != settle and not args.force:
        print(f"今天 {today} 不是結算日（本月第三個週三 = {settle}）。測試請加 --force")
        return 0

    try:
        q0 = fetch_spot(session, args.stock)
    except Exception as e:
        if replay_mode:
            raise ReplaySourceError("twse_spot: 沒有有效報價") from e
        raise
    if replay_mode and not (q0["last"] or q0["prev_close"]):
        raise ReplaySourceError("twse_spot: 沒有有效現貨價格")
    if replay_mode and not (q0["limit_up"] and q0["limit_dn"]):
        raise ReplaySourceError("twse_spot: 沒有有效漲跌停價")
    if not (q0["limit_up"] and q0["limit_dn"]):
        print("[warn] 抓不到漲跌停價，鎖定區間無法計算（收盤後測試屬正常）")
    print(f"[settlement_monitor] {args.stock} {q0['name']}｜昨收 {q0['prev_close']}"
          f"｜漲停 {q0['limit_up']}｜跌停 {q0['limit_dn']}")
    print(f"結算均價 = 12:30（不含）–13:25 每 5 秒快照 660 個 + 收盤價，共 {TOTAL_SAMPLES} 個的平均\n")

    current = now()
    start = current.replace(hour=12, minute=30, second=5, microsecond=0)
    if current < start and not args.force:
        wait = (start - current).total_seconds()
        print(f"等待 12:30:05 開始取樣（{wait / 60:.1f} 分鐘）…")
        sleep(max(0, wait))
    if (
        not replay_mode
        and not args.force
        and now() > start + timedelta(seconds=SAMPLE_LATE_TOLERANCE_SECONDS)
    ):
        print(
            "[error] 已錯過 12:30:05 第一個正式取樣時點；"
            "無法重建完整 660 筆盤中樣本",
            file=sys.stderr,
        )
        return 1

    samples: list[float] = []
    last_price = q0["last"] or q0["prev_close"]
    locked_announced = False
    futures_enabled = bool(args.futures_symbol) and not (
        replay_mode and replay["futures_warning"]
    )
    if replay_mode:
        intraday_target = TOTAL_SAMPLES - 1
    elif args.max_iter:
        intraday_target = min(args.max_iter, TOTAL_SAMPLES - 1)
    elif args.force:
        intraday_target = 12
    else:
        intraday_target = TOTAL_SAMPLES - 1
    absolute_schedule = replay_mode or not args.force

    while len(samples) < intraday_target:
        if absolute_schedule:
            sample_at = start + timedelta(seconds=len(samples) * 5)
            current = now()
            if current < sample_at:
                sleep((sample_at - current).total_seconds())
            if now() > sample_at + timedelta(
                seconds=SAMPLE_LATE_TOLERANCE_SECONDS
            ):
                message = (
                    "twse_spot: 已錯過正式 5 秒取樣時點 "
                    f"{sample_at.strftime('%H:%M:%S')}"
                )
                if replay_mode:
                    raise ReplaySourceError(message)
                print(f"[error] {message}", file=sys.stderr)
                return 1
        elif samples:
            sleep(5)
        try:
            q = fetch_spot(session, args.stock)
            if q["last"]:
                last_price = q["last"]
        except Exception as e:
            if replay_mode:
                raise ReplaySourceError("twse_spot: 沒有有效報價") from e
            print(f"[warn] {e}")
        samples.append(last_price)             # 無成交時沿用前一筆（與交易所揭示邏輯一致）

        n = len(samples)
        m = sum(samples) / n
        remain = max(TOTAL_SAMPLES - n, 0)
        lu, ld = q0["limit_up"], q0["limit_dn"]
        if lu and ld:
            hi = (sum(samples) + remain * lu) / TOTAL_SAMPLES
            lo = (sum(samples) + remain * ld) / TOTAL_SAMPLES
        else:
            hi = lo = m
        tick = tick_size(last_price)

        stamp = now().strftime("%H:%M:%S")
        line = (f"[{stamp}] n={n:3d}/{TOTAL_SAMPLES} 價={last_price:.2f} "
                f"均={m:.4f} 鎖定區間=[{lo:.2f}, {hi:.2f}] 寬={hi - lo:.3f}")
        print(line)

        if not locked_announced and lu and ld and (hi - lo) < tick and n > 60:
            locked_announced = True
            inner_lo = round((int(lo / tick)) * tick, 2)
            inner_hi = round(inner_lo + tick, 2)
            emit_alert(
                "🔒 SOP-3 結算價模型區間縮窄",
                f"{args.stock} {q0['name']} 模型估計區間 ≈ [{lo:.2f}, {hi:.2f}]\n"
                f"參考跳動刻度：{inner_lo} 至 {inner_hi}。\n"
                f"請人工核對樣本完整性、tick 與正式結算規則；本警報不保證結算價，也不代表下單建議。",
                cfg,
                replay_mode=replay_mode,
            )

        if futures_enabled:
            fp = fetch_futures(
                session,
                args.futures_symbol,
                strict_source=replay_mode,
            )
            if replay_mode and fp is None:
                futures_enabled = False
            if fp and last_price:
                basis = last_price - fp
                pct = basis / last_price * 100
                print(f"          期貨 {fp:.2f}｜期現價差 {basis:+.2f}（{pct:+.2f}%）")
                if abs(pct) >= float(cfg.get("basis_alert_pct", 0.5)):
                    emit_alert(
                        "↔️ SOP-4 期現價差擴大",
                        f"{args.stock} 現貨 {last_price:.2f} vs 期貨 {fp:.2f} "
                        f"= {basis:+.2f}（{pct:+.2f}%）\n"
                        f"價差已達監控門檻。請人工核對資料時間戳、券源、交易成本、流動性與價格延續性。\n"
                        f"本警報不代表建立、調整或平倉任何部位。",
                        cfg,
                        replay_mode=replay_mode,
                        sound=not locked_announced,
                    )

    if intraday_target == TOTAL_SAMPLES - 1:
        print("盤中樣本已收滿 660 筆；等待 13:30 收盤價")
        close_ready = now().replace(
            hour=13, minute=30, second=10, microsecond=0
        )
        if not replay_mode and now() < close_ready:
            sleep((close_ready - now()).total_seconds())
        try:
            close_quote = fetch_spot(session, args.stock)
            close_price = close_quote["last"]
        except Exception as e:
            if replay_mode:
                raise ReplaySourceError("twse_spot: 沒有有效收盤價") from e
            print(f"[error] 無法取得有效收盤價: {e}", file=sys.stderr)
            return 1
        if not close_price:
            if replay_mode:
                raise ReplaySourceError("twse_spot: 沒有有效收盤價")
            print("[error] 無法取得有效收盤價", file=sys.stderr)
            return 1
        samples.append(close_price)
        stamp = now().strftime("%H:%M:%S")
        print(
            f"[{stamp}] 收盤價={close_price:.2f} "
            f"n={len(samples)}/{TOTAL_SAMPLES}"
        )

    print(f"\n最終估計均值 {sum(samples) / len(samples):.4f}（樣本 {len(samples)} 筆）")
    print("提醒：正式結算價以期交所公告為準（含收盤價那一筆）。")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", help="現貨代號，例 2603")
    ap.add_argument("--futures-symbol", default="", help="TAIFEX MIS 股期代號（選填，SOP-4 用）")
    ap.add_argument("--force", action="store_true", help="忽略結算日/時段檢查（測試）")
    ap.add_argument("--max-iter", type=int, default=0, help="最多抓幾次（0=直到 13:30）")
    ap.add_argument(
        "--replay",
        type=Path,
        metavar="CASE_DIR",
        help="從 scenario.json 與原始 fixture 時序執行確定性離線重播",
    )
    args = ap.parse_args(argv)
    if not args.replay and not args.stock:
        ap.error("the following arguments are required: --stock")
    try:
        replay = load_replay_case(args.replay) if args.replay else None
        return run(args, replay)
    except ReplayScenarioError as e:
        print(f"[error] replay scenario 無效: {e}", file=sys.stderr)
        return 2
    except ReplaySourceError as e:
        print(f"[error] replay 來源無效: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
