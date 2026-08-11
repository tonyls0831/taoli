# -*- coding: utf-8 -*-
"""SOP-2 台指期遠近月價差表：除權息蒸發點數 → 合理價差 → 跳動警報。

做的事（每天收盤後或盤前跑一次）：
1. 抓 TWSE 除權除息預告（TWT48U_ALL），只取「除息」現金股利（除權不蒸發指數）。
2. 用 收盤價×發行股數 算全市場市值 → 每點市值 → 每筆除息的指數蒸發點數。
3. 按台指期結算日（第三個週三）分桶：
   D_near = 今天 ~ 近月結算日 的蒸發點數
   D_cross = 近月結算日 ~ 次月結算日 的蒸發點數
   合理價差（次月−近月）≈ −(D_cross + 避險逆價差)
4. 對照 TAIFEX 盤後資料的實際近/次月收盤價差。
5. 與上次執行的合理價差 diff：跳動 ≥ 門檻（預設 10 點）→ 警報（= 馬克羊說的
   「某公司預估除息日跨過結算日邊界」的訊號）。
6. 輸出 markdown 報告到 vault 的 data/ 資料夾。

限制：只算「已公告」的除權息；馬克羊的完整版還會自己猜未公告的大權值股。
"""
import json
import re
from datetime import date

from common import (DATA_DIR, load_config, make_session, notify, now_taipei,
                    roc_to_date, settlement_dates_from, contract_code)

STATE_FILE = DATA_DIR / "dividend_spread_state.json"


def fetch_json(session, url):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def get_market_cap_per_point(session) -> tuple[float, float, dict[str, float]]:
    """回傳 (每點市值(元), 指數值, {股票代號: 發行股數})。"""
    comp = fetch_json(session, "https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
    shares: dict[str, float] = {}
    for row in comp:
        code = (row.get("公司代號") or "").strip()
        n = (row.get("已發行普通股數或TDR原股發行股數") or "0").replace(",", "")
        try:
            shares[code] = float(n)
        except ValueError:
            pass

    quotes = fetch_json(session, "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    closes: dict[str, float] = {}
    for row in quotes:
        code = (row.get("Code") or "").strip()
        c = (row.get("ClosingPrice") or "").replace(",", "")
        try:
            closes[code] = float(c)
        except ValueError:
            pass

    total_cap = sum(closes[c] * s for c, s in shares.items() if c in closes)

    # 加權指數即時值（收盤後為最後值）
    r = session.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
                    params={"ex_ch": "tse_t00.tw", "json": "1", "delay": "0"}, timeout=10)
    arr = r.json().get("msgArray", [])
    idx = None
    for f in ("z", "y", "pz"):
        v = (arr[0].get(f) if arr else "") or ""
        try:
            idx = float(v)
            break
        except ValueError:
            continue
    if not idx:
        raise RuntimeError("抓不到加權指數值")
    return total_cap / idx, idx, shares


def get_dividend_events(session, shares: dict[str, float],
                        cap_per_point: float) -> list[dict]:
    """已公告的除息事件 → [{date, code, name, cash, points}]，按日期排序。"""
    rows = fetch_json(session, "https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL")
    events = []
    for row in rows:
        d = roc_to_date(row.get("Date", ""))
        code = (row.get("Code") or "").strip()
        try:
            cash = float((row.get("CashDividend") or "0").replace(",", "") or 0)
        except ValueError:
            cash = 0.0
        if not d or cash <= 0 or code not in shares:
            continue
        pts = cash * shares[code] / cap_per_point
        events.append({"date": d.isoformat(), "code": code,
                       "name": (row.get("Name") or "").strip(),
                       "cash": cash, "points": round(pts, 2)})
    events.sort(key=lambda e: e["date"])
    return events


def get_market_spread(session, near_code: str, next_code: str):
    """TAIFEX 盤後：TX 近月/次月（一般時段）收盤價 → (近月價, 次月價, 價差, 日期)。"""
    today = now_taipei().date()
    start = today.replace(day=1) if today.day > 7 else (today.replace(day=1))
    r = session.post("https://www.taifex.com.tw/cht/3/futDataDown",
                     data={"down_type": "1", "commodity_id": "TX",
                           "queryStartDate": (today.replace(day=1)).strftime("%Y/%m/%d"),
                           "queryEndDate": today.strftime("%Y/%m/%d")},
                     timeout=30)
    r.raise_for_status()
    lines = r.content.decode("big5", errors="replace").splitlines()
    best: dict[str, tuple[str, float]] = {}   # 月份 -> (交易日期, 收盤價)  取最新一般時段
    for ln in lines[1:]:
        f = [x.strip() for x in ln.split(",")]
        if len(f) < 18 or f[1] != "TX" or not re.fullmatch(r"\d{6}", f[2]):
            continue
        session_type = f[17] if len(f) > 17 else ""
        if session_type and "一般" not in session_type:
            continue
        price_s = f[6] if f[6] not in ("-", "") else f[10]   # 收盤價，缺就用結算價
        try:
            price = float(price_s)
        except ValueError:
            continue
        month = f[2]
        if month not in best or f[0] > best[month][0]:
            best[month] = (f[0], price)
    if near_code in best and next_code in best:
        near_p, next_p = best[near_code][1], best[next_code][1]
        return near_p, next_p, next_p - near_p, best[near_code][0]
    return None


def main():
    cfg = load_config()
    session = make_session()
    today = now_taipei().date()

    print("[1/4] 計算每點市值 …")
    cap_per_point, idx, shares = get_market_cap_per_point(session)
    print(f"      加權指數 {idx:,.0f}｜全市場市值 {cap_per_point * idx / 1e12:,.1f} 兆｜每點 ≈ {cap_per_point / 1e8:,.1f} 億")

    print("[2/4] 抓除權息預告、算蒸發點數 …")
    events = get_dividend_events(session, shares, cap_per_point)

    settles = settlement_dates_from(today, 3)
    near_s, next_s = settles[0], settles[1]
    d_near = sum(e["points"] for e in events if today < date.fromisoformat(e["date"]) <= near_s)
    d_cross = sum(e["points"] for e in events if near_s < date.fromisoformat(e["date"]) <= next_s)
    hedge = float(cfg.get("hedge_discount_points", 5))
    fair = -(d_cross + hedge)

    print("[3/4] 抓 TAIFEX 近/次月實際價差 …")
    near_code, next_code = contract_code(near_s), contract_code(next_s)
    mkt = None
    try:
        mkt = get_market_spread(session, near_code, next_code)
    except Exception as e:
        print(f"[warn] TAIFEX 價差抓取失敗: {e}")

    # ---- 與上次比較（跨界跳動警報）----
    prev = {}
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    prev_fair = prev.get("fair")
    jump = (fair - prev_fair) if (prev_fair is not None and prev.get("near") == near_code) else None
    STATE_FILE.write_text(json.dumps(
        {"date": today.isoformat(), "near": near_code, "next": next_code,
         "d_near": round(d_near, 1), "d_cross": round(d_cross, 1), "fair": round(fair, 1)},
        ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 報告 ----
    lines = [
        f"# 除權息價差表 {today.isoformat()}",
        "",
        f"- 加權指數：{idx:,.0f}（每點市值 ≈ {cap_per_point / 1e8:,.1f} 億元）",
        f"- 近月合約：{near_code}（結算 {near_s}）｜次月：{next_code}（結算 {next_s}）",
        f"- **D_near**（今天→近月結算的蒸發點數）：**{d_near:,.1f} 點**",
        f"- **D_cross**（近月→次月結算的蒸發點數）：**{d_cross:,.1f} 點**",
        f"- **合理價差（次月−近月）≈ −({d_cross:,.1f} + {hedge:g} 避險) = {fair:,.1f} 點**",
    ]
    if jump is not None:
        lines.append(f"- 與上次（{prev.get('date')}）比較：合理價差變動 **{jump:+.1f} 點**")
    if mkt:
        near_p, next_p, spread, mdate = mkt
        gap = spread - fair
        lines += [
            f"- 市場價差（{mdate} 收盤）：{next_p:,.0f} − {near_p:,.0f} = **{spread:,.1f} 點**",
            f"- **市場 − 合理 = {gap:+.1f} 點**"
            + ("（次月相對太貴 → 檢視「買近月＋空次月」）" if gap > 0 else
               "（次月相對太便宜 → 檢視「空近月＋買次月」）"),
        ]
    lines += ["", f"## 除息事件明細（{today} → {next_s}，共 "
              f"{sum(1 for e in events if today < date.fromisoformat(e['date']) <= next_s)} 筆）", "",
              "| 除息日 | 代號 | 名稱 | 現金股利 | 蒸發點數 | 桶 |", "|---|---|---|---|---|---|"]
    for e in events:
        d = date.fromisoformat(e["date"])
        if not (today < d <= next_s):
            continue
        bucket = "近月" if d <= near_s else "**次月**"
        lines.append(f"| {e['date']} | {e['code']} | {e['name']} | {e['cash']:.2f} | {e['points']:.2f} | {bucket} |")

    report = "\n".join(lines) + "\n"
    out = DATA_DIR / f"除權息價差_{today.isoformat()}.md"
    out.write_text(report, encoding="utf-8")
    print(f"[4/4] 報告已寫入 {out}")
    print("\n" + "\n".join(lines[:12]))

    # ---- 警報 ----
    if jump is not None and abs(jump) >= float(cfg.get("spread_jump_alert", 10)):
        notify("📊 SOP-2 合理價差跳動",
               f"合理價差 {prev_fair:+.1f} → {fair:+.1f}（{jump:+.1f} 點）\n"
               f"通常＝某大權值股除息日估計跨過結算日邊界。\n"
               f"請人工核對除息資料、估計日期、市場價差、流動性與風險條件。\n"
               f"本警報不代表任何部位條件已成立。", cfg)
    if mkt and abs(mkt[2] - fair) >= float(cfg.get("spread_gap_alert", 8)):
        notify("📊 SOP-2 市場價差偏離合理值",
               f"市場 {mkt[2]:+.1f} vs 合理 {fair:+.1f}（差 {mkt[2] - fair:+.1f} 點）\n"
               f"注意：這是用「已公告」除息算的合理值，請檢查未公告權值股與資料時點。\n"
               f"這是模型差異觀察，不代表交易指示。", cfg)


if __name__ == "__main__":
    main()
