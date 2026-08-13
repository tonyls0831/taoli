# -*- coding: utf-8 -*-
"""SOP-5 盤前簡報產生器（台北時間早上 07:00–08:20 之間跑）。

內容 = 馬克羊的盤前功課清單：
1. 美股四大指數（道瓊、S&P500、那斯達克、費半）＋ 台積電 ADR 漲跌
2. 台指期夜盤（盤後時段）收盤與漲跌
3. 今日除權息名單：現金股利、昨收、除息參考價、除息幅度（>10% 標記為 SOP-5 觀察股）
4. 昨日三大法人買賣超 Top（外資、投信）
輸出 markdown 到 vault/盤前簡報/YYYY-MM-DD.md，並可推播摘要。
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from common import (VAULT_DIR, load_config, make_session, notify, now_taipei,
                    roc_to_date)

BRIEF_DIR = VAULT_DIR / "盤前簡報"

YAHOO = {"道瓊": "^DJI", "S&P500": "^GSPC", "那斯達克": "^IXIC",
         "費城半導體": "^SOX", "台積電ADR": "TSM"}


class ReplayScenarioError(Exception):
    """離線重播 scenario 不符合公開 Interface。"""


class ReplaySourceError(Exception):
    """離線重播的具名外部資料來源無效。"""


class ReplayResponse:
    def __init__(self, *, payload=None, content: bytes = b""):
        self._payload = payload
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class ReplaySession:
    """以 scenario 內的原始 payload 取代外部市場資料 HTTP 邊界。"""

    def __init__(self, sources: dict):
        self.sources = sources

    def get(self, url: str, *, params=None, timeout=None):
        if "query1.finance.yahoo.com" in url:
            symbol = url.rsplit("/", 1)[-1]
            return ReplayResponse(payload=self.sources["yahoo"][symbol])
        if url.endswith("/TWT48U_ALL"):
            return ReplayResponse(payload=self.sources["twse_dividends"])
        if url.endswith("/STOCK_DAY_ALL"):
            return ReplayResponse(payload=self.sources["twse_closes"])
        if url.endswith("/T86"):
            query_date = (params or {}).get("date")
            return ReplayResponse(payload=self.sources["twse_t86"].get(query_date, {}))
        raise ReplayScenarioError(f"scenario 未宣告 GET request: {url}")

    def post(self, url: str, *, data=None, timeout=None):
        if url.endswith("/futDataDown"):
            return ReplayResponse(content=self.sources["taifex_night"])
        raise ReplayScenarioError(f"scenario 未宣告 POST request: {url}")


def _fixture_path(case_dir: Path, source_name: str, relative_path) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ReplayScenarioError(f"{source_name}: fixture 路徑必須是非空字串")
    path = (case_dir / relative_path).resolve()
    try:
        path.relative_to(case_dir)
    except ValueError as e:
        raise ReplayScenarioError(f"{source_name}: fixture 路徑不得離開 case-dir") from e
    if not path.is_file():
        raise ReplayScenarioError(f"{source_name}: 找不到 fixture {relative_path}")
    return path


def _load_json_fixture(case_dir: Path, source_name: str, relative_path):
    path = _fixture_path(case_dir, source_name, relative_path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise ReplayScenarioError(
            f"{source_name}: fixture JSON 無效 ({type(e).__name__})"
        ) from e


def load_replay_case(case_dir: Path) -> tuple[datetime, ReplaySession]:
    case_dir = case_dir.resolve()
    scenario_path = case_dir / "scenario.json"
    try:
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ReplayScenarioError("找不到 scenario.json") from e
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise ReplayScenarioError(
            f"scenario.json 無效 ({type(e).__name__})"
        ) from e
    if not isinstance(scenario, dict):
        raise ReplayScenarioError("scenario.json 頂層必須是物件")
    if scenario.get("schema_version") != 1:
        raise ReplayScenarioError("schema_version 必須是 1")
    try:
        run_at = datetime.fromisoformat(scenario["run_at"])
    except (KeyError, TypeError, ValueError) as e:
        raise ReplayScenarioError("run_at 必須是 ISO 8601 日期時間") from e
    if run_at.utcoffset() != timedelta(hours=8):
        raise ReplayScenarioError("run_at 必須明確使用 +08:00 時區")

    sources = scenario.get("sources")
    if not isinstance(sources, dict):
        raise ReplayScenarioError("sources 必須是物件")
    yahoo_paths = sources.get("yahoo")
    if not isinstance(yahoo_paths, dict) or set(yahoo_paths) != set(YAHOO.values()):
        raise ReplayScenarioError("yahoo 必須宣告五個固定商品")
    t86_paths = sources.get("twse_t86")
    if not isinstance(t86_paths, dict) or not t86_paths:
        raise ReplayScenarioError("twse_t86 必須宣告至少一個查詢日期")

    loaded = {
        "yahoo": {
            symbol: _load_json_fixture(
                case_dir, f"yahoo[{symbol}]", yahoo_paths[symbol]
            )
            for symbol in YAHOO.values()
        },
        "twse_dividends": _load_json_fixture(
            case_dir, "twse_dividends", sources.get("twse_dividends")
        ),
        "twse_closes": _load_json_fixture(
            case_dir, "twse_closes", sources.get("twse_closes")
        ),
        "twse_t86": {
            query_date: _load_json_fixture(
                case_dir, f"twse_t86[{query_date}]", relative_path
            )
            for query_date, relative_path in t86_paths.items()
        },
    }
    taifex_path = _fixture_path(
        case_dir, "taifex_night", sources.get("taifex_night")
    )
    try:
        loaded["taifex_night"] = taifex_path.read_text(
            encoding="utf-8"
        ).encode("big5")
    except (OSError, UnicodeError) as e:
        raise ReplayScenarioError(
            f"taifex_night: fixture CSV 無效 ({type(e).__name__})"
        ) from e
    return run_at, ReplaySession(loaded)


def yahoo_quote(session, symbol: str, *, strict_source: bool = False):
    r = session.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                    params={"range": "5d", "interval": "1d"}, timeout=15)
    r.raise_for_status()
    try:
        res = r.json()["chart"]["result"][0]
        closes = [
            c for c in res["indicators"]["quote"][0]["close"]
            if c is not None
        ]
    except (KeyError, IndexError, TypeError) as e:
        if strict_source:
            raise ReplaySourceError(
                f"yahoo[{symbol}]: payload 格式無效"
            ) from e
        raise
    if len(closes) < 2:
        if strict_source:
            raise ReplaySourceError(
                f"yahoo[{symbol}]: 沒有兩筆有效收盤價"
            )
        return None
    last, prev = closes[-1], closes[-2]
    return last, (last - prev) / prev * 100


def night_session_tx(session, today: date | None = None):
    """台指期近月「盤後」時段最新收盤與漲跌%。"""
    today = today or now_taipei().date()
    r = session.post("https://www.taifex.com.tw/cht/3/futDataDown",
                     data={"down_type": "1", "commodity_id": "TX",
                           "queryStartDate": today.replace(day=1).strftime("%Y/%m/%d"),
                           "queryEndDate": today.strftime("%Y/%m/%d")},
                     timeout=30)
    r.raise_for_status()
    lines = r.content.decode("big5", errors="replace").splitlines()
    rows = []
    for ln in lines[1:]:
        f = [x.strip() for x in ln.split(",")]
        if len(f) >= 18 and f[1] == "TX" and re.fullmatch(r"\d{6}", f[2]) and "盤後" in (f[17] or ""):
            rows.append(f)
    if not rows:
        return None
    rows.sort(key=lambda f: (f[0], f[2]))
    latest_date = rows[-1][0]
    near = [f for f in rows if f[0] == latest_date][0]
    return latest_date, near[2], near[6], near[7], near[8]   # 日期, 月份, 收盤, 漲跌, 漲跌%


def today_dividends(session, today: date | None = None):
    """今日除息名單 + 參考價。"""
    rows = session.get("https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL",
                       timeout=30).json()
    quotes = session.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
                         timeout=30).json()
    close = {}
    for q in quotes:
        try:
            close[q["Code"].strip()] = float(q["ClosingPrice"].replace(",", ""))
        except (ValueError, AttributeError, KeyError):
            pass
    today = today or now_taipei().date()
    out = []
    for row in rows:
        if roc_to_date(row.get("Date", "")) != today:
            continue
        code = (row.get("Code") or "").strip()
        try:
            cash = float((row.get("CashDividend") or "0").replace(",", "") or 0)
        except ValueError:
            cash = 0.0
        prev = close.get(code)
        ref = (prev - cash) if (prev and cash) else None
        pct = (cash / prev * 100) if (prev and cash) else 0
        out.append({"code": code, "name": (row.get("Name") or "").strip(),
                    "cash": cash, "prev": prev, "ref": ref, "pct": pct})
    out.sort(key=lambda x: -x["pct"])
    return out


def t86_top(session, today: date | None = None):
    """昨交易日三大法人買賣超 Top10（外資/投信，張）。"""
    from datetime import timedelta
    d = today or now_taipei().date()
    for back in range(1, 6):
        qd = d - timedelta(days=back)
        r = session.get("https://www.twse.com.tw/rwd/zh/fund/T86",
                        params={"date": qd.strftime("%Y%m%d"), "selectType": "ALL",
                                "response": "json"}, timeout=30)
        j = r.json()
        if j.get("stat") == "OK" and j.get("data"):
            fields, data = j["fields"], j["data"]
            i_code, i_name = 0, 1
            i_foreign = next(i for i, f in enumerate(fields) if "外陸資買賣超" in f)
            i_trust = next(i for i, f in enumerate(fields) if f.startswith("投信買賣超"))

            def parse(rows, idx):
                out = []
                for row in rows:
                    try:
                        v = int(row[idx].replace(",", "")) // 1000
                        out.append((row[i_code].strip(), row[i_name].strip(), v))
                    except (ValueError, IndexError):
                        pass
                return out

            f_all = parse(data, i_foreign)
            t_all = parse(data, i_trust)
            f_all.sort(key=lambda x: x[2])
            t_all.sort(key=lambda x: x[2])
            return qd, {"外資買超": f_all[::-1][:10], "外資賣超": f_all[:10],
                        "投信買超": t_all[::-1][:10], "投信賣超": t_all[:10]}
    return None, {}


def build_brief(session, run_at: datetime, *, replay: bool = False):
    today = run_at.date()
    lines = [f"# 盤前簡報 {today.isoformat()}（{'一二三四五六日'[today.weekday()]}）", ""]

    # 1. 美股
    lines += ["## 美股（前一交易日）", ""]
    summary = []
    for name, sym in YAHOO.items():
        try:
            q = yahoo_quote(session, sym, strict_source=replay)
            if q:
                lines.append(f"- {name}：{q[0]:,.2f}（{q[1]:+.2f}%）")
                summary.append(f"{name} {q[1]:+.1f}%")
        except Exception as e:
            if replay and isinstance(e, ReplaySourceError):
                raise
            lines.append(f"- {name}：抓取失敗（{type(e).__name__}）")
    lines.append("")

    # 2. 夜盤
    lines += ["## 台指期夜盤", ""]
    try:
        ns = night_session_tx(session, today)
        if ns:
            lines.append(f"- {ns[0]} 夜盤 {ns[1]}：收 {ns[2]}（{ns[3]}｜{ns[4]}）")
            summary.append(f"夜盤 {ns[4]}")
        else:
            lines.append("- 無夜盤資料")
    except Exception as e:
        lines.append(f"- 夜盤抓取失敗（{type(e).__name__}）")
    lines.append("")

    # 3. 今日除權息
    divs = []
    try:
        divs = today_dividends(session, today)
    except Exception as e:
        lines.append(f"（除權息名單抓取失敗：{e}）")
    lines += [f"## 今日除息名單（{len(divs)} 檔）", ""]
    if divs:
        lines += ["| 代號 | 名稱 | 現金股利 | 昨收 | 除息參考價 | 幅度 | SOP-5 |",
                  "|---|---|---|---|---|---|---|"]
        for e in divs:
            flag = "⭐觀察" if e["pct"] >= 10 else ""
            ref_text = f"{e['ref']:.2f}" if e["ref"] else "-"
            lines.append(f"| {e['code']} | {e['name']} | {e['cash']:.2f} | "
                         f"{e['prev'] or '-'} | "
                         f"{ref_text} | "
                         f"{e['pct']:.1f}% | {flag} |")
        big = [e for e in divs if e["pct"] >= 10]
        if big:
            summary.append("除息>10%: " + "、".join(f"{e['name']}({e['pct']:.0f}%)" for e in big[:3]))
            lines += ["", "> ⭐ 幅度 >10% ＝「看起來變便宜」行為效應最強 → 按 SOP-5：",
                      "> 8:30 看試撮、**8:43 期貨禁刪單後** 判斷開盤價合理性（對大盤/ADR/同族群）"]
    else:
        lines.append("（今日無除息）")
    lines.append("")

    # 4. 三大法人
    qd, tops = t86_top(session, today)
    if tops:
        lines += [f"## 三大法人買賣超（{qd}，張）", ""]
        for k, rows in tops.items():
            lines.append(f"**{k}**：" + "、".join(f"{n}({v:+,})" for c, n, v in rows[:5]))
        lines.append("")

    if replay:
        lines += [
            "---",
            "> 本離線重播僅供盤前研究與人工核對，不是下單或交易授權。",
            "",
        ]
    lines += ["---", "產生時間：" + run_at.strftime("%Y-%m-%d %H:%M:%S"),
              "資料源：Yahoo Finance / TAIFEX / TWSE OpenAPI / TWSE T86"]
    return lines, summary


def _replay_output_path(case_dir: Path, output_dir: Path, run_at: datetime) -> Path:
    case_dir = case_dir.resolve()
    output_dir = output_dir.resolve()
    formal_brief_dir = BRIEF_DIR.resolve()
    for protected_dir, message in (
        (case_dir, "output-dir 不得位於 replay case-dir 內"),
        (formal_brief_dir, "output-dir 不得位於正式盤前簡報目錄"),
    ):
        try:
            output_dir.relative_to(protected_dir)
        except ValueError:
            pass
        else:
            raise ReplayScenarioError(message)
    return output_dir / f"{run_at.date().isoformat()}.md"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--replay",
        type=Path,
        help="從 scenario.json 與原始 fixture payload 執行確定性離線重播",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="replay 簡報的明示安全輸出目錄（不得使用正式盤前簡報目錄）",
    )
    args = parser.parse_args(argv)
    if bool(args.replay) != bool(args.output_dir):
        parser.error("--replay 與 --output-dir 必須同時使用")

    if args.replay:
        try:
            run_at, session = load_replay_case(args.replay)
            lines, _ = build_brief(session, run_at, replay=True)
            out = _replay_output_path(args.replay, args.output_dir, run_at)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("x", encoding="utf-8", newline="\n") as report:
                report.write("\n".join(lines) + "\n")
        except ReplaySourceError as e:
            print(f"[error] replay source 無效: {e}", file=sys.stderr)
            return 1
        except (ReplayScenarioError, FileExistsError) as e:
            print(f"[error] replay scenario 無效: {e}", file=sys.stderr)
            return 2
        print(f"離線重播 {run_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"簡報已寫入 {out}")
        return 0

    cfg = load_config()
    session = make_session()
    run_at = now_taipei()
    lines, summary = build_brief(session, run_at)

    BRIEF_DIR.mkdir(exist_ok=True)
    out = BRIEF_DIR / f"{run_at.date().isoformat()}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"簡報已寫入 {out}\n")
    print("\n".join(lines[:25]))

    if summary:
        notify(f"📋 盤前簡報 {run_at.date()}", "｜".join(summary) + f"\n完整版：{out.name}", cfg, sound=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
