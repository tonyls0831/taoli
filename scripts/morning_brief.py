# -*- coding: utf-8 -*-
"""SOP-5 盤前簡報產生器（台北時間早上 07:00–08:20 之間跑）。

內容 = 馬克羊的盤前功課清單：
1. 美股四大指數（道瓊、S&P500、那斯達克、費半）＋ 台積電 ADR 漲跌
2. 台指期夜盤（盤後時段）收盤與漲跌
3. 今日除權息名單：現金股利、昨收、除息參考價、除息幅度（>10% 標記為 SOP-5 觀察股）
4. 昨日三大法人買賣超 Top（外資、投信）
輸出 markdown 到 vault/盤前簡報/YYYY-MM-DD.md，並可推播摘要。
"""
import re
from datetime import date

from common import (VAULT_DIR, load_config, make_session, notify, now_taipei,
                    roc_to_date)

BRIEF_DIR = VAULT_DIR / "盤前簡報"
BRIEF_DIR.mkdir(exist_ok=True)

YAHOO = {"道瓊": "^DJI", "S&P500": "^GSPC", "那斯達克": "^IXIC",
         "費城半導體": "^SOX", "台積電ADR": "TSM"}


def yahoo_quote(session, symbol: str):
    r = session.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                    params={"range": "5d", "interval": "1d"}, timeout=15)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    if len(closes) < 2:
        return None
    last, prev = closes[-1], closes[-2]
    return last, (last - prev) / prev * 100


def night_session_tx(session):
    """台指期近月「盤後」時段最新收盤與漲跌%。"""
    today = now_taipei().date()
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


def today_dividends(session):
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
    today = now_taipei().date()
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


def t86_top(session):
    """昨交易日三大法人買賣超 Top10（外資/投信，張）。"""
    from datetime import timedelta
    d = now_taipei().date()
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


def main():
    cfg = load_config()
    session = make_session()
    today = now_taipei().date()
    lines = [f"# 盤前簡報 {today.isoformat()}（{'一二三四五六日'[today.weekday()]}）", ""]

    # 1. 美股
    lines += ["## 美股（前一交易日）", ""]
    summary = []
    for name, sym in YAHOO.items():
        try:
            q = yahoo_quote(session, sym)
            if q:
                lines.append(f"- {name}：{q[0]:,.2f}（{q[1]:+.2f}%）")
                summary.append(f"{name} {q[1]:+.1f}%")
        except Exception as e:
            lines.append(f"- {name}：抓取失敗（{type(e).__name__}）")
    lines.append("")

    # 2. 夜盤
    lines += ["## 台指期夜盤", ""]
    try:
        ns = night_session_tx(session)
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
        divs = today_dividends(session)
    except Exception as e:
        lines.append(f"（除權息名單抓取失敗：{e}）")
    lines += [f"## 今日除息名單（{len(divs)} 檔）", ""]
    if divs:
        lines += ["| 代號 | 名稱 | 現金股利 | 昨收 | 除息參考價 | 幅度 | SOP-5 |",
                  "|---|---|---|---|---|---|---|"]
        for e in divs:
            flag = "⭐觀察" if e["pct"] >= 10 else ""
            lines.append(f"| {e['code']} | {e['name']} | {e['cash']:.2f} | "
                         f"{e['prev'] or '-'} | "
                         f"{f'{e['ref']:.2f}' if e['ref'] else '-'} | "
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
    qd, tops = t86_top(session)
    if tops:
        lines += [f"## 三大法人買賣超（{qd}，張）", ""]
        for k, rows in tops.items():
            lines.append(f"**{k}**：" + "、".join(f"{n}({v:+,})" for c, n, v in rows[:5]))
        lines.append("")

    lines += ["---", "產生時間：" + now_taipei().strftime("%Y-%m-%d %H:%M:%S"),
              "資料源：Yahoo Finance / TAIFEX / TWSE OpenAPI / TWSE T86"]

    out = BRIEF_DIR / f"{today.isoformat()}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"簡報已寫入 {out}\n")
    print("\n".join(lines[:25]))

    if summary:
        notify(f"📋 盤前簡報 {today}", "｜".join(summary) + f"\n完整版：{out.name}", cfg, sound=False)


if __name__ == "__main__":
    main()
