# Codex 遷移完成計畫

狀態：已由 repository owner 於 2026-08-12 確認；由 GitHub Issue #3 追蹤
版本日期：2026-08-12

## 目的

本文件定義 Taoli 從 Phase 6 到正式宣布 Codex 遷移完成的工作範圍、驗收條件、
安全邊界與建議 GitHub ticket 拆分。它延續 Phase 5 已驗證的
Issue → TDD → branch → CI → review → squash merge 流程。

這是一份遷移完成規格，不是交易策略規格，也不是自動交易計畫。完成遷移後，
市場規則、資料端點與研究內容仍須進入一般維護週期，不會因遷移完成而永久有效。

## 現況基準

截至 2026-08-12：

- Codex 已是主要 agent，專案預設模型為 `gpt-5.6-sol`，推理強度為 `xhigh`。
- Private repository、GitHub Issues、triage labels 與 Python 3.10／3.14 CI 已建立。
- Phase 5 已用 Issue #1 與 PR #2 完成第一輪 Codex-native delivery loop。
- `typhoon_watch.py --once --source-file <fixture.html>` 是第一個經 owner 確認的
  public replay seam。
- Claude chat、JSONL 與 memory 只是歷史資料，不再是執行期依賴；目前不刪除它們。
- 專案仍只有研究、監控、計算、報告與通知能力，不連接券商或自動下單。

## 遷移完成的定義

只有下列條件全部成立，才可在 `docs/project-context.md` 宣布
「Codex migration complete」：

1. **Repository 可獨立理解**：新的 Codex task 不讀舊 chat 或 Claude memory，
   只靠 tracked 文件即可說明專案定位、領域詞彙、安全邊界與工作流程。
2. **單一正式工作入口**：新的工程工作以 GitHub Issues 為準，並能追溯到 spec、
   branch、測試、PR、review 與 merge 結果。
3. **重複交付證據**：除 Phase 5 外，至少再完成一輪獨立的
   Issue → TDD → PR → CI → review → merge。
4. **確定性離線驗證**：四支 Python 工具都至少有一個經 owner 確認的 public seam，
   並有可重播的代表性 happy-path fixture 與清楚的外部資料失敗案例。
5. **支援版本受保護**：Python 3.10／3.14 CI 持續通過，且 `main` 的必要保護規則
   不能繞過這些 checks。
6. **機密狀態清楚**：tracked tree 與 Git history 完成 secret audit；已知 secret、
   webhook、token、`.env`、`config.json` 或 runtime state 不存在於 repository history。
   若發現疑似機密，先停止、回報並由 owner 決定輪替與清除方式。
7. **乾淨環境可重建**：從新的暫存 clone，依 tracked 文件即可安裝依賴、執行 tests、
   compile scripts 與 parse `.codex/config.toml`。
8. **真實資料再認證**：四支工具的現行公開資料路徑均有具日期、來源與結果的受控
   smoke-test 紀錄；關鍵規則以 DGPA、TWSE、TAIFEX 等 primary source 為準。
9. **Cold-start 驗收**：全新的 Codex task 能在不依賴本對話的情況下完成一張小型
   ticket，並遵守人工執行與外部寫入限制。
10. **無遷移 blocker**：所有 migration tickets 已完成，或已被 owner 明確轉成
    一般維護 ticket；剩餘限制已寫入 durable docs，不藏在 chat 裡。

## 全程安全與範圍邊界

- 監控警報只代表需要人工檢查，不是買賣建議或下單授權。
- 不連接券商、不加入帳戶金鑰、不建立自動下單或部位管理。
- 不以 live polling loop、外部通知、排程或 runtime state 作為一般驗證手段。
- Fixtures 不含 token、cookie、個人資料或不必要的完整第三方頁面內容。
- 真實資料驗證必須是單次、限時、唯讀且限定資料路徑；執行前另取得 owner 授權。
- GitHub repository settings、labels、Issues、PRs、remotes 與 branch deletion 都是
  external writes；依專案規則取得明確授權後才執行。
- Claude 歷史資料預設保留。封存、移動或刪除必須另行明確授權，且不屬於遷移
  完成的必要條件。
- 本計畫不要求窮舉所有 HTML／JSON 變形；重點是代表性路徑、清楚失敗與可維護 seam。

## Phase 6：確定性 replay coverage

### 目標

把 Phase 5 驗證成功的 fixture-backed testing 模式擴展到四支工具的關鍵公開資料
邊界，使主要解析與計算路徑不依賴即時網站也能回歸驗證。

### Phase 6A：補強颱風監控

- 保留既有 normal-operation fixture。
- 增加停班警報 fixture，驗證輸出仍要求人工核對且不產生交易指令。
- 增加缺少臺北市或無有效資料的 fixture，驗證失敗或降級訊息清楚。
- 視實際 parser 風險增加最小 malformed-markup case；不建立大量脆弱 snapshots。
- CLI integration test 只觀察 exit code 與 console；filesystem safety 由獨立 safety
  regression 驗證。
- 所有 replay cases 必須不連網、不蜂鳴、不推播、不產生設定或 runtime state。

### Phase 6B–6D：其餘工具

依序處理：

1. `dividend_spread.py`
2. `settlement_monitor.py`
3. `morning_brief.py`

每支工具採兩張票：

1. **Seam decision**：盤點外部資料邊界、輸出副作用與日期依賴，提出最小 public CLI
   seam；必須由 owner 確認後才寫 integration test。
2. **Replay implementation**：以一個 tracer-bullet fixture 寫 red test，只實作足以
   green 的離線重播能力，再增加一個清楚的資料失敗案例。

不得事先假定 `--source-file` 適合所有工具；多來源工具可選擇經確認的 fixture
directory、manifest 或其他單一 public interface。測試不得 mock 專案內部函式。

### Phase 6 驗收

- 四支工具各有 owner-confirmed public seam。
- 每支工具至少有一個代表性 happy path 與一個外部資料失敗案例。
- Replay tests 在無網路、無通知、無排程、無 runtime state 下可重複執行。
- Python 3.10／3.14 CI 全綠。
- 每個 implementation ticket 各自完成 Standards + Spec review。

## Phase 7：Repository 治理、機密與可重建性

### 目標

讓 `main` 的品質門檻、工程入口與機密邊界不依賴某一次對話或某一位 agent 的記憶。

### 工作項目

- 由 owner 確認 branch-protection policy。建議預設：
  - PR 合併前要求 Python 3.10 與 Python 3.14 checks；
  - 禁止 force push 與 branch deletion；
  - solo repository 暫不強制外部 reviewer，避免 owner 無法合併自己的 PR。
- 建立精簡的 Issue／PR templates，要求 spec、public seam、驗證、安全與外部寫入欄位。
- 稽核 tracked tree 與 Git history 的疑似 secrets，只回報檔案／commit 位置與類型，
  不輸出 secret 值。
- 檢查 ignore rules 是否涵蓋 `.env*`、`scripts/config.json`、runtime state、logs、
  videos、`.claude/` 與 Obsidian local state。
- 在新的暫存 clone 執行文件化安裝與完整離線驗證，記錄任何隱藏依賴。

### Phase 7 驗收

- `main` 保護規則符合 owner 核准的 policy，required checks 能實際阻擋失敗 merge。
- Issue／PR templates 已可用，且不把 PR 當成未經 triage 的需求入口。
- Secret audit 有日期、範圍與結論；疑似機密均有明確處置決定。
- Clean-clone validation 通過，或所有 blocker 已修正並重新驗證。

## Phase 8：真實資料來源再認證

### 目標

證明離線 fixtures 所代表的資料形狀仍對應目前公開來源，並把時間敏感事實與歷史
fixture 清楚分離。

### 執行規則

- 每支工具一張 recertification ticket，逐一取得 owner 對限定 live read 的授權。
- 只執行單次、限時、唯讀 smoke test；不啟動 polling loop、不發通知、不建立排程。
- 若現有 CLI 不能安全做到單次驗證，先回 Phase 6 增加經確認的安全 seam。
- 每次紀錄：驗證日期、endpoint／官方頁面、工具版本或 commit、結果、偏差與已知限制。
- 市場規則與正式數值以 primary official source 為準；免費或非正式 endpoint 只能作為
  工具資料來源，不能取代正式公告。
- 若 endpoint 已失效，必須修復、替換、明確停用或記錄 owner 接受的限制；不能以舊
  fixture 假裝目前仍可用。

### Phase 8 驗收

- 四支工具都有不早於本 Phase 執行日的 recertification 紀錄。
- 每個現行資料路徑都有「可用、已替換、已停用或 owner 接受限制」之一的明確結論。
- 文件保留驗證日期與來源，不把即時值回寫成過去已知的歷史事實。

## Phase 9：Cold-start 驗收與遷移關閉

### 目標

驗證 Codex 能在沒有本次對話與 Claude memory 的情況下獨立操作此 repository，然後
正式結束遷移計畫。

### 工作項目

- 建立一張範圍小、低風險、可在單一 PR 完成的 acceptance ticket。
- 從全新的 Codex task 開始，只提供 repository 與 ticket，不引用舊 chat。
- 完成 context reading、branch、test、review、PR、CI 與 merge 全流程。
- 搜尋 tracked files、scripts 與文件，確認沒有 Claude-specific runtime dependency。
- 確認 Claude 歷史資料的保留狀態是明示決定，而不是隱藏依賴。
- 更新 `docs/project-context.md`：記錄完成日期、acceptance Issue／PR／commit、
  已知限制與後續維護入口。
- 關閉 migration tracking issue；未完成但不阻擋遷移的事項轉成一般維護 Issues。

### Phase 9 驗收

- Cold-start acceptance ticket 已合併且 main CI 全綠。
- Repository-only context 足以完成工作，沒有讀取舊 Claude memory 才能前進的步驟。
- Definition of Done 十項全部有可追溯證據。
- Durable context 明確標記 Codex 遷移完成，並停止使用 Phase 編號管理一般維護。

## 建議 ticket 拆分

以下為本 spec 核准後的 ticket batch。票號由 GitHub 建立時決定；`blocked by` 應
使用 native dependency，無法使用時才回退到 issue body。

| 暫定 ID | GitHub Issue | Ticket | 建議角色 | Blocking |
|---|---|---|---|---|
| M0 | #3 | Track Codex migration completion | tracking | — |
| P6-1 | #4 | Add typhoon alert and missing-data replay cases | `ready-for-agent` | — |
| P6-2 | #5 | Decide `dividend_spread.py` replay seam | `ready-for-human` | — |
| P6-3 | #6 | Implement dividend-spread replay slice | `ready-for-agent` | P6-2 |
| P6-4 | #7 | Decide `settlement_monitor.py` replay seam | `ready-for-human` | — |
| P6-5 | #8 | Implement settlement replay slice | `ready-for-agent` | P6-4 |
| P6-6 | #9 | Decide `morning_brief.py` replay seam | `ready-for-human` | — |
| P6-7 | #10 | Implement morning-brief replay slice | `ready-for-agent` | P6-6 |
| P7-1 | #11 | Approve main branch-protection policy | `ready-for-human` | Phase 6 |
| P7-2 | #12 | Apply repository governance and templates | `ready-for-agent` | P7-1 |
| P7-3 | #13 | Audit secrets, ignore rules, and clean-clone reproducibility | `ready-for-agent` | Phase 6 |
| P8-1 | #14 | Authorize bounded live-source recertification | `ready-for-human` | Phase 6 |
| P8-2 | #15 | Recertify `typhoon_watch.py` sources | `ready-for-agent` | P8-1 |
| P8-3 | #16 | Recertify `dividend_spread.py` sources | `ready-for-agent` | P8-1, P6-3 |
| P8-4 | #17 | Recertify `settlement_monitor.py` sources | `ready-for-agent` | P8-1, P6-5 |
| P8-5 | #18 | Recertify `morning_brief.py` sources | `ready-for-agent` | P8-1, P6-7 |
| P9-1 | #19 | Run repository-only cold-start acceptance | `ready-for-agent` | Phase 7, Phase 8 |
| P9-2 | #20 | Declare Codex migration complete | `ready-for-agent` | P9-1 |

`ready-for-human` tickets代表需要 owner 作決定或授權；決定完成後，受其阻擋的
implementation ticket 才進入 agent 工作佇列。由本計畫直接產生的 implementation
tickets 已有 spec，不再走 incoming-request triage。

## Ticket 與 PR 的共同驗證要求

每張會修改程式或文件的 implementation ticket 應包含：

- 明確 scope 與 non-goals；
- 已確認的 public seam，或指向已完成的 seam-decision ticket；
- 一個 tracer-bullet red → green slice；
- 一般驗證無網路／通知／排程／runtime-state 的安全說明；
- `python -m unittest discover -s tests -v`；
- `python -m compileall -q scripts`；
- `.codex/config.toml` parse；
- 受影響 CLI 的 `--help` 與最小安全 targeted test；
- `git diff --check`；
- Standards + Spec code review；
- draft PR、CI、owner merge approval 與 closeout 紀錄。

Phase 8 recertification tickets 是上述「一般驗證無網路」的唯一預先定義例外；它們只在
owner 對該 ticket 明確授權後執行 bounded live read，且仍不得發通知、建立排程或寫入
runtime state。純 GitHub settings 或稽核 tickets 則執行與其風險相稱的 applicable
checks，並保存可追溯證據，不為了湊齊命令而修改程式。

只有對應 ticket 明確授權時，才可執行 GitHub settings 修改、live network read、
外部通知、排程、歷史重寫、secret rotation 或檔案刪除。

## Owner 已確認項目

Repository owner 已於 2026-08-12 確認以下預設：

1. 同意以 Phase 6–9 與本文件的十項 Definition of Done 作為遷移完成標準。
2. 同意 Phase 6 的順序為 typhoon → dividend → settlement → morning brief。
3. 同意 Phase 7 branch protection 採「required CI、禁止 force push／branch deletion、
   暫不強制外部 reviewer」的 solo-repository 預設。
4. 同意 Phase 8 每支工具仍須在各自 ticket 中取得限定 live-read 授權。
5. 同意 Claude 歷史資料預設保留，刪除不列為遷移 blocker。
6. 同意確認後建立一張 tracking issue 與上表 child tickets／blocking dependencies。
