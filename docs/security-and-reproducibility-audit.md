# Security and reproducibility audit

稽核日期：2026-08-13（Asia/Taipei）

追蹤 Issue：#13

基準 commit：`d11a20930c7b917ecb026d73625a579767d25a0c`

本文件只記錄稽核範圍、位置類型與結果，不保存或顯示 secret 值。

## Secret audit

範圍包括基準 commit 的 119 個 tracked files，以及所有 refs 可達的 16 個 commits
（最早 `45bcb6e`，截至 `d11a209`）。兩組獨立的 pathname／blob 掃描涵蓋：

- private-key blocks；
- GitHub、AWS、Slack、Discord、Telegram token／webhook pattern；
- JWT、credentialed URL 與常見 non-empty credential assignment；
- `.env*`、`config.json`、`*_state.json`、logs、key/certificate stores、archives／DB、
  `.claude/`、`videos/`、Obsidian workspace／plugin bundle 等敏感檔名。

結果：tracked tree 與完整可達 history 皆無高信心 credential 或敏感檔名命中。
沒有疑似 secret 需要 rotation、history rewrite 或 owner escalation。

## Ignore coverage

以 `git check-ignore` 實證下列本機 artifacts 均受保護：

| 類別 | 規則 |
|---|---|
| Environment | 完整 `.env*`（含 `.envrc`／`.envrc.local`）；保留可追蹤 `!.env.example` |
| Runtime config | `/scripts/config.json` |
| Runtime state | `/data/*_state.json` |
| Logs | `*.log` |
| Large/local sources | `/videos/`、`/.claude/` |
| Obsidian local state | `/.obsidian/workspace*.json`、`/.obsidian/plugins/`、`/.trash/` |

`.obsidian/app.json`、`appearance.json`、`community-plugins.json`、`core-plugins.json`
是刻意追蹤的共享 vault 設定；內容結構與 credential scan 均無命中。未發現 ignore gap。

Code Review 額外發現原規則 `.env`／`.env.*` 沒有涵蓋 `.envrc`；已修正為完整
`.env*`。`git check-ignore --no-index` 的空白 filename probes 證實 `.env`、
`.env.local`、`.envrc`、`.envrc.local` 均 ignored，而 `.env.example` 保持可追蹤。

## Hidden dependency and repair

稽核發現 `scripts/common.py` 在 import time 使用 `ZoneInfo("Asia/Taipei")`。原本 README
與 CI 只直接安裝 `requests`、`beautifulsoup4`；在沒有 system IANA timezone database 的
clean Windows Python 上，這會隱含依賴本機額外安裝的 `tzdata`。

修正方式：建立 tracked `requirements.txt`，統一宣告 `requests`、`beautifulsoup4`、
`tzdata`；README 與 CI 都改用同一 `-r requirements.txt` 安裝入口。此 manifest 刻意不
鎖 patch version，保留 Python 3.10／3.14 相容更新；CI matrix 持續驗證實際相容性。

## Clean-clone validation

從 remote `agent/reproducibility-audit` 的 commit
`c778ba66c3c986d49637ac80579d938c25106eae` 建立全新 Windows temporary clone 與全新
venv；temporary root 的 leaf name 是
`taoli-clean-clone-b950e31141264b379e765bfb73e8d356`，驗證後移除。環境為 Python
3.14.4、pip 26.0.1，未沿用本 repository 的 venv 或 site-packages。

依 tracked 文件執行：

1. `python -m pip install --disable-pip-version-check -r requirements.txt`
2. `python -m unittest discover -s tests -v`
3. `python -m compileall -q scripts`
4. 以 `tomllib` parse `.codex/config.toml`
5. `git diff --check`

結果：

- requirements 安裝成功，實際取得 `requests 2.34.2`、`beautifulsoup4 4.15.0`、
  `tzdata 2026.3` 與其 dependencies；
- 31 個 tests 通過，僅 1 個明確標註為 CI Python 3.10 matrix 才執行的 local skip；
- compile、TOML parse、`git diff --check` 全部通過；
- 忽略 `.clean-venv/` 後，tracked worktree 為 clean。

結論：tracked files 足以在新的 Windows Python 3.14 環境完成安裝與完整離線驗證；
原先的 timezone hidden dependency 已修復。Python 3.10 由 PR CI matrix 另行驗證。
