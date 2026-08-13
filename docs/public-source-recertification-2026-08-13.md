# 公開資料來源再認證（2026-08-13）

本紀錄保存 GitHub Issues #15–#18 的 Phase 8 bounded live-read 證據。核驗日皆為
2026-08-13（Asia/Taipei）；live reads 固定於 `main`
`3ed297df31dbfe2bbf74e6a2e2d05c6d9e445f89`。除特別註明的最小診斷與修復後
重測外，每個端點只讀一次，停用重試與 redirect，資料只留在記憶體。

所有 probe 都以一次性的 `python -` 行程執行既有 source/parser function，沒有呼叫
工具的 `run()` 或 polling loop；沒有讀寫 `scripts/config.json`、runtime state 或報告，
沒有通知、蜂鳴、排程、券商連線或下單。Issue #18 核准的安全輸出目標
`%TEMP%\taoli-morning-brief-recert-20260813` 也沒有建立。以下結果只代表核驗當日的
來源與 parser 狀態，不是持續可用性保證或交易授權。

## 狀態摘要

| Issue／資料路徑 | 分類 | 結論 |
|---|---|---|
| #15 DGPA 停班停課頁 | usable | 當日無城市公告時能清楚得到空結果；活動公告列仍需在事件發生時重驗。 |
| #16 TWSE 公司股數、收盤價、除權息 | usable | OpenAPI shape 可解析；除權息模型只涵蓋已公告事件。 |
| #16 TWSE MIS 加權指數 | owner-accepted limitation | fallback 欄位可解析，但免費 MIS shape 非正式且脆弱。 |
| #16 TAIFEX 盤後期貨 CSV | usable | Big5 CSV 多一欄但必要欄位與 TX 一般時段 parser 相容。 |
| #17 TWSE MIS 個股報價 | usable | `msgArray` 與必要 fallback 欄位相容。 |
| #17 TAIFEX MIS 選用股期報價 | owner-accepted limitation | 現行 symbol 可由官方資料形成，但單次 POST 回傳 HTTP error，未證明 payload shape。 |
| #18 Yahoo 五個市場 symbol | owner-accepted limitation | parser 成功，但 Yahoo 是非官方、無 SLA 的 provider。 |
| #18 TAIFEX 夜盤、TWSE 除權息／收盤價、T86 | usable | parser 成功；TWSE 無關的零收盤列已以公開 replay regression 修復。 |

`usable` 只表示這次 bounded probe 與既有 fixture/parser 相容；交易所或政府正式公告
仍是規則、休市、結算價與市場事實的最終依據。

## Issue #15：`typhoon_watch.py`

### Bounded command 與來源

- Invocation：下列 sanitized command 是實際 `python -` probe 的可重現等價形式；只輸出
  response metadata、markup count 與 parser count，不輸出公告內容：

```powershell
python -c "import sys; sys.path.insert(0,'scripts'); from urllib3.util.retry import Retry; from common import make_session; from typhoon_watch import URL,parse_status_html; s=make_session(('www.dgpa.gov.tw',)); [setattr(a,'max_retries',Retry(total=0)) for a in s.adapters.values()]; r=s.get(URL,timeout=20,allow_redirects=False); p=parse_status_html(r.text); print({'status':r.status_code,'bytes':len(r.content),'tables':r.text.count('<table'),'cities':len(p),'taipei':'臺北市' in p})"
```

- 以 `make_session(("www.dgpa.gov.tw",))` 建立既有 relaxed-SSL session，adapter retry
  設為 0。
- 單次 GET：`https://www.dgpa.gov.tw/typh/daily/nds.html`，timeout 20 秒，
  `allow_redirects=False`；只將 response body 交給實際的 `parse_status_html()`。
- 結果：HTTP 200、`text/html`、15,036 bytes、無 `Location`；頁面 title 為
  「行政院人事行政總處全球資訊網-天然災害停止上班及上課情形查詢」。

### Shape、parser 與分類

Live markup 有 1 個 table、3 個 `tr`、0 個 `thead tr`、2 個 `tbody tr`，但沒有任何
含至少 2 個 `td` 的城市資料列；parser 得到 0 個城市，臺北市不存在，標準化空 mapping
SHA-256 為 `44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`。

三個 replay fixture 都有 1 個 table；城市資料列為 1–2 列、parser 城市為 1–2 個，
normal 與 suspension case 含臺北市，missing-Taipei case 不含。Live response 的 table
與總列數仍在 fixture 範圍，但 `thead`、城市 cell row 與 parsed-city count 不同。

分類為 **usable**，範圍限於目前「無城市公告／空 mapping」狀態：來源可達、官方頁面
身分正確且 parser 能清楚降級。這次沒有活動公告列，因此 fixture 仍是離線 regression，
不能當作現行活動公告 markup 的證明；下次實際公告時應再做一次 bounded recertification。
DGPA 頁面只確認停班停課公告 context，不據此推論交易所休市或結算規則。

## Issue #16：`dividend_spread.py`

### Bounded command 與來源

Invocation 為單一 `python -` probe；每列各一次，停用 retry／redirect，只呼叫既有
fetch/parser functions，不執行合理價差報告：

```powershell
python -c "import sys; sys.path.insert(0,'scripts'); from datetime import date; from urllib3.util.retry import Retry; from common import make_session; from dividend_spread import get_market_cap_per_point,get_dividend_events,get_market_spread; s=make_session(('openapi.twse.com.tw','mis.twse.com.tw','www.taifex.com.tw')); [setattr(a,'max_retries',Retry(total=0)) for a in s.adapters.values()]; g,p=s.get,s.post; s.get=lambda url,**kw:g(url,allow_redirects=False,**kw); s.post=lambda url,**kw:p(url,allow_redirects=False,**kw); cap,idx,shares=get_market_cap_per_point(s,strict_sources=True); events=get_dividend_events(s,shares,cap,strict_sources=True); futures=get_market_spread(s,'202608','202609',date(2026,8,13),strict_source=True); print({'shares':len(shares),'index_ok':idx>0,'events':len(events),'futures_ok':futures is not None})"
```

這個 command 的 helper request manifest 如下；表單與 query parameters 是 command 的
一部分，輸出不含指數、期貨價格或合理價差：

| Method／timeout | Endpoint | Live 結果 |
|---|---|---|
| GET／30s | `https://openapi.twse.com.tw/v1/opendata/t187ap03_L` | HTTP 200；list 1,095 列，1,095 列有公司代號與普通股／TDR 股數欄，parser 1,095 列。 |
| GET／30s | `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` | HTTP 200；list 1,379 列，必要 `Code`／`ClosingPrice` shape 可供市值 parser 使用。 |
| GET／10s | `https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0` | HTTP 200；dict／`msgArray` 1 列；`z`／`y`／`pz` fallback 得到有效指數。實際 timeout 依程式為 10s，非授權留言誤載的 15s。 |
| GET／30s | `https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL` | HTTP 200；list 137 列，92 列有有效正現金股利日期；與股數 join 後得到 86 個事件，日期範圍 2026-08-11 至 2026-10-07。 |
| POST／30s | `https://www.taifex.com.tw/cht/3/futDataDown`；form `down_type=1`、`commodity_id=TX`、`queryStartDate=2026/08/01`、`queryEndDate=2026/08/13` | HTTP 200；Big5 CSV 19 欄／214 列；54 列為 TX 一般時段，日期 2026-08-03 至 2026-08-13；近／次月 parser 成功。 |

OpenAPI fixtures 保留同名原始欄位與最小列；live 的公司股數、收盤價與 TWT48U 必要欄位
相容。TAIFEX live CSV 比 fixture 的 18 欄多 1 欄，但 parser 依 header 名稱取值，沒有因
欄位增加失敗。TWSE MIS fixture 同時示範 `z`、`y`、`pz`，live 列未同時具備全部欄位；
既有 fallback 仍得到一個有效指數，因此此路徑分類為 **owner-accepted limitation**。

公司股數、收盤價、TWT48U 與 TAIFEX CSV 分類為 **usable**。TWT48U 只包含已公告的
除權息事件；未公告的大權值股或未確定日期不會進入模型，可能低估跨月桶，這是保留的
owner-accepted limitation。Probe 沒有輸出 live fair spread；模型結果仍須人工核對。

### 官方規則核對

- [TWSE 指數編製規則](https://twse-regulation.twse.com.tw/TW/law/DOC01_print.aspx?FLCODE=FL047579&FLNO=5)：除息時價格指數基值不調整。
- [TWSE 除權除息預告表](https://www.twse.com.tw/zh/announcement/ex-right/twt48u.html)與[計算結果／公式](https://www.twse.com.tw/zh/announcement/ex-right/twt49u.html)：確認 TWT48U 的公告 context 與除權息計算入口。
- [TAIFEX 臺股期貨契約](https://www.taifex.com.tw/cht/2/tX?menuid1=12)：最後交易日／結算日為交割月份第三個星期三；遇假日或不可抗力依官方規則調整。
- [TAIFEX 盤後資料下載](https://www.taifex.com.tw/cht/3/dlFutDailyMarketView)：確認盤後 CSV 的官方下載 context。

最初 Issue 留言只泛稱 official pages，沒有逐頁列出 URL，屬程序偏差。補記
[exact-page restatement](https://github.com/tonyls0831/taoli/issues/16#issuecomment-5279340553)
後，上列五個 exact pages 各以 timeout 15 秒、零 retry／redirect 單次重讀；皆為
HTTP 200、HTML 且 page title 符合預期。完成結果保存於
[Issue #16](https://github.com/tonyls0831/taoli/issues/16#issuecomment-5279354976)。

## Issue #17：`settlement_monitor.py`

### Bounded command、quote feeds 與分類

兩個 quote endpoint 均只執行一次；沒有進入 5 秒 polling loop：

```powershell
python -c "import requests; from requests.adapters import HTTPAdapter; s=requests.Session(); s.mount('https://',HTTPAdapter(max_retries=0)); p=s.get('https://mis.twse.com.tw/stock/api/getStockInfo.jsp',params={'ex_ch':'tse_2330.tw','json':'1','delay':'0'},timeout=10,allow_redirects=False).json(); q=p.get('msgArray',[{}])[0]; print({'rows':len(p.get('msgArray',[])),'fields_present':all(k in q for k in ('z','y','pz','u','w','n','t'))})"
python -c "import requests; from requests.adapters import HTTPAdapter; s=requests.Session(); s.mount('https://',HTTPAdapter(max_retries=0)); r=s.post('https://mis.taifex.com.tw/futures/api/getQuoteDetail',json={'SymbolID':'CDFH6-F'},timeout=10,allow_redirects=False); print({'status':r.status_code,'content_type':r.headers.get('Content-Type',''),'bytes':len(r.content),'location_present':bool(r.headers.get('Location'))})"
```

- TWSE：`python -` 單次 GET
  `https://mis.twse.com.tw/stock/api/getStockInfo.jsp`，參數
  `ex_ch=tse_2330.tw&json=1&delay=0`，timeout 10 秒。HTTP 200，top-level dict、
  `msgArray` 1 列，`z`／`y`／`pz`／`u`／`w`／`n`／`t` 均存在，last price 可解析。
  與 fixture 的 `msgArray: [object]` 及 fallback 欄位相容，分類為 **usable**。Production
  會以 `tse_{stock}.tw|otc_{stock}.tw` 同時查上市／上櫃；本次依核准參數只驗證上市代號。
- TAIFEX：先由 [TAIFEX 期貨大額交易人未沖銷部位結構表](https://www.taifex.com.tw/cht/3/largeTraderFutQryTbl)
  確認台積電期貨有 2026/08 契約，再由 [TWSE ISIN 期貨與選擇權清單](https://isin.twse.com.tw/isin/e_C_public.jsp?strMode=6)
  精確確認當期代號 `CDFH6`，形成 endpoint convention `CDFH6-F`；接著以單次 POST
  `https://mis.taifex.com.tw/futures/api/getQuoteDetail`，JSON
  `{"SymbolID":"CDFH6-F"}`，timeout 10 秒。第一次請求得到 generic HTTP error；經
  [Issue #17 留言](https://github.com/tonyls0831/taoli/issues/17#issuecomment-5279240337)
  記錄的同 request、status-only 診斷得到 HTTP 400、`application/json`、547 bytes、
  無 redirect。診斷沒有讀取或解析 body，因此仍無法比對 fixture 的
  `RtData.QuoteList[]`／`RtData.Quote{}` shape，分類為
  **owner-accepted limitation**。選用期貨路徑不影響必要 TWSE replay。

最初 Issue 留言未精確列出後來用於 symbol discovery 的兩頁，屬程序偏差。補記
[exact-page restatement](https://github.com/tonyls0831/taoli/issues/17#issuecomment-5279341453)
後，兩個 symbol pages 與三個 rule／contract pages 各以 timeout 15 秒、零
retry／redirect 單次重讀；皆為 HTTP 200，ISIN 頁為 Big5 HTML 且其餘 title 符合預期。
完成結果保存於 [Issue #17](https://github.com/tonyls0831/taoli/issues/17#issuecomment-5279355090)。

### 正式結算規則與修正

[TAIFEX 股票期貨最後結算價公式](https://www.taifex.com.tw/cht/5/formulaStock)確認：
到期日證券市場收盤前 60 分鐘，若標的是指數成分股，使用 12:30（不含）至 13:25
（含）的每次指數揭示時點標的價格，再加最後一筆收盤指數，取簡單平均並四捨五入至
小數第二位。[TWSE 指數編製規則](https://twse-regulation.twse.com.tw/TW/law/DOC01_print.aspx?FLCODE=FL047579&FLNO=4)
確認盤中每 5 秒揭示；因此 660 個 5 秒樣本加收盤價共 661 筆。

[TAIFEX 股票期貨契約規格](https://www.taifex.com.tw/cht/2/sTF)另確認 500 元至未滿
2,500 元的最小升降單位為 1 元。Live recert 發現 replay 原從 12:30:00 起算，且程式在
1,000 元以上誤用 5 元 tick。修復以公開 CLI 先得到兩個 red，再於 commit `8cc6ba0`
改為第一筆 12:30:05，並將 1 元級距延伸至未滿 2,500 元；完整 settlement replay／
safety suite 11 項通過。

Code Review 另發現 production 原本在每次 HTTP 完成後固定 sleep 5 秒，會把 request
latency 累積進 cadence。現在 live path 以 12:30:05 為絕對錨點，逐筆排到 13:25:00；
晚啟動或錯過任一正式 5 秒時點超過 1 秒就清楚失敗，不會把延遲樣本或 13:25 後報價
冒充完整序列。公開 replay regression 明確核對第一筆 12:30:05、最後盤中一筆
13:25:00、盤中 660 筆完成訊息與獨立收盤價。

模型鎖定區間只是使用正式公式前提的研究估計，不是 TAIFEX 公告的正式結算價，也不代表
下單建議。

## Issue #18：`morning_brief.py`

### Bounded command 與來源結果

Invocation 為單一 `python -` in-memory probe；安全輸出目標沒有建立：

```powershell
@'
import sys
sys.path.insert(0, "scripts")
from datetime import date
from urllib3.util.retry import Retry
from common import make_session
from morning_brief import YAHOO, yahoo_quote, night_session_tx, today_dividends, t86_top

s = make_session()
for adapter in s.adapters.values():
    adapter.max_retries = Retry(total=0)
get, post = s.get, s.post
s.get = lambda url, **kwargs: get(url, allow_redirects=False, **kwargs)
s.post = lambda url, **kwargs: post(url, allow_redirects=False, **kwargs)

def probe(name, operation):
    try:
        print({name: operation()})
    except Exception as error:
        print({name: type(error).__name__})

for symbol in YAHOO.values():
    probe(f"yahoo[{symbol}]", lambda symbol=symbol: yahoo_quote(s, symbol, strict_source=True) is not None)
probe("taifex_night", lambda: night_session_tx(s, date(2026, 8, 13), strict_source=True) is not None)
probe("twse_dividends", lambda: len(today_dividends(s, date(2026, 8, 13), strict_source=True)))
probe("twse_t86", lambda: (lambda result: {"date": result[0].isoformat(), "categories": len(result[1])})(t86_top(s, date(2026, 8, 13), strict_source=True)))
'@ | python -
```

Request manifest：Yahoo 每個 symbol 都帶 query `range=5d&interval=1d`；TAIFEX form
為 `down_type=1`、`commodity_id=TX`、`queryStartDate=2026/08/01`、
`queryEndDate=2026/08/13`；T86 每次帶 `date=YYYYMMDD`、`selectType=ALL`、
`response=json`，從 2026-08-12 往前最多五次並在第一個 `stat=OK` 停止。上述保存的
failure-isolated command 對每個 provider 獨立 try/catch，所以 dividend parser 失敗不會
阻止 T86 bounded read；輸出只含 parser boolean/count 或 exception type。

| Method／timeout | Endpoint／範圍 | Fixture／parser 結果與分類 |
|---|---|---|
| GET／15s，各一次 | `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`；`^DJI`、`^GSPC`、`^IXIC`、`^SOX`、`TSM` | 五個 response 都有兩個 finite closes，與 chart fixture 相容；**owner-accepted limitation**（非官方、無 SLA）。 |
| POST／30s，一次 | `https://www.taifex.com.tw/cht/3/futDataDown` | Big5 TX 夜盤 parser 成功，得到 2026-08-13 的日期／契約／收盤／漲跌 shape；**usable**。 |
| GET／30s，各一次 | `TWT48U_ALL` 與 `STOCK_DAY_ALL` | 修復後 strict parser 得到當日 7 個事件，欄位與 fixture 相容且數值皆 finite；**usable**。 |
| GET／30s，找到第一個 OK 即停 | `https://www.twse.com.tw/rwd/zh/fund/T86` | 在核准的最多 5 個交易日回溯內，2026-08-12 成功；4 個分類、每類 10 列，與 fixture shape 相容；**usable**。 |

第一次 TWSE strict probe 發現 `STOCK_DAY_ALL` 1,379 列中有 12 列收盤價非正數，雖然
當日 7 個除權息代號都有有效收盤價，parser 仍在 join 前整批失敗。另一次核准的最小診斷
只輸出 shape/error category count；公開 replay regression 隨後先 red，再於 commit
`bef9b8214290184619d092656d6bbdee217cdf75` 改為略過不相關的無效收盤列，同時保留「當日
事件缺有效收盤價就點名來源失敗」的必要保護。修復後只重讀兩個 TWSE endpoint 各一次，
strict parser 成功且沒有輸出證券或價格。

初次、診斷與修復後重測各自的 exact TWSE requests 均為 GET
`TWT48U_ALL` 與 GET `STOCK_DAY_ALL`、timeout 30 秒；診斷 command 只計算
`other_date`／`valid_today`／`nonpositive_close`／`today_code_has_close` 類別數，重測
command 只執行 `today_dividends(session, date(2026,8,13), strict_source=True)` 並輸出
result count、keys 與 `all_numeric_finite`。兩次額外 reads 的事前 manifests 分別保存於
[diagnostic 留言](https://github.com/tonyls0831/taoli/issues/18#issuecomment-5278996616)與
[post-fix retest 留言](https://github.com/tonyls0831/taoli/issues/18#issuecomment-5279019145)。

### 官方事實與非官方限制

- [TWSE 除權息計算結果／公式](https://www.twse.com.tw/zh/announcement/ex-right/twt49u.html)確認除權息資訊的官方計算 context。
- [TWSE T86 商品說明](https://eshop.twse.com.tw/zh/product/detail/c4c87ac184e44896a05fcab5a9d544ec)確認每日三大法人買賣超資料與欄位 context。
- [TAIFEX 期貨每日行情](https://www.taifex.com.tw/cht/3/futDailyMarketView)確認盤後／夜盤資料入口與日期 context。
- Yahoo Finance 僅作盤前觀察資料，不能取代交易所正式資料；availability、調整方式與 symbol shape 都沒有本專案可依賴的 SLA。

最初 Issue 留言只泛稱 official pages，沒有逐頁列出 URL，屬程序偏差。補記
[exact-page restatement](https://github.com/tonyls0831/taoli/issues/18#issuecomment-5279341268)
後，上列三個 exact pages 各以 timeout 15 秒、零 retry／redirect 單次重讀；皆為
HTTP 200、HTML 且 page title 符合預期。完成結果保存於
[Issue #18](https://github.com/tonyls0831/taoli/issues/18#issuecomment-5279355465)。

## 使用與再認證條件

- 關鍵日執行前仍應做最小、單次 source smoke test；不要用 full polling loop 當驗證。
- DGPA 出現活動公告、TWSE／TAIFEX schema 或商品規格改變、TAIFEX MIS 恢復或更換 quote
  path、Yahoo chart shape 改變時，重新走 replay fixture 比對並新增 dated evidence。
- 公開資料錯誤、延遲、缺漏或非正式端點失效時，工具應清楚失敗或停用選用路徑，不得以
  舊值冒充即時值。
- 任何 alert、模型區間、價差或簡報都是 observation／research output，仍由人工作規則、
  流動性、成本、資料時間戳與正式公告核對；不構成交易指令。
