# Taoli agent guide

## Project purpose

This Obsidian vault researches market rules, event-driven trading ideas, and the
public-data monitoring tools derived from the Mark Yang / Dr. Yang Zhen video
archive. It is a research and decision-support project, not an automated trading
system.

## Read before working

1. Read `CONTEXT.md` for the canonical domain vocabulary.
2. Read `docs/project-context.md` for project history, source hierarchy, current
   capabilities, and known limitations.
3. For strategy content, read `馬克羊交易策略系統性分析.md` and the relevant
   section of `套利操作SOP.md`.
4. Before changing Python tools, read `scripts/README.md` and the affected script.
5. Read relevant ADRs under `docs/adr/` if that directory exists.

Do not rely on imported chat history or Claude memory as the only source of
project context; the tracked files above are the durable source.

## Repository map

- `馬克羊交易策略系統性分析.md`: synthesized analysis and source attribution.
- `套利操作SOP.md`: human-execution procedures and risk conditions.
- `transcripts/`: tracked `.txt` and `.srt` evidence generated from source media.
- `scripts/`: public-data monitoring, calculation, reporting, and notification
  helpers. They do not place orders.
- `data/`: generated research reports; runtime `*_state.json` files are ignored.
- `盤前簡報/`: dated pre-market research outputs.
- `videos/`: large local source media, intentionally ignored by Git.

## Evidence and financial-safety rules

- Keep these categories distinct: source claim, transcript evidence, project
  analysis, current market fact, and monitoring alert.
- Treat transcripts as machine-generated. Verify wording against audio/video
  before presenting an exact quotation or making a decision that turns on one
  word or number.
- Market rules, schedules, instruments, endpoints, and live values are
  time-sensitive. Re-check current claims against primary official sources such
  as DGPA, TWSE, and TAIFEX, and state the verification date.
- A script alert is an observation, not a recommendation or authorization to
  trade. Preserve the project's human-execution boundary.
- Never place an order, connect a brokerage account, automate order entry, send
  an external notification, or create a scheduled job unless the user explicitly
  requests that specific external action.
- Do not present historical performance claims as independently audited results.
  Retain caveats about capacity, liquidity, execution, regime change, and edge
  decay.

## Editing conventions

- Use Traditional Chinese for user-facing project notes unless the surrounding
  document is intentionally English.
- Preserve UTF-8, existing Obsidian wikilinks, and dated-file naming conventions.
- Keep historical reports historical. Add a dated correction or clearly marked
  update instead of silently rewriting a past observation as though it was known
  at the original date.
- Store durable conclusions in tracked documents, not chat-only memory.
- Keep `CONTEXT.md` as a glossary only. Put implementation state and project
  history in `docs/project-context.md`; record only genuinely hard-to-reverse,
  surprising trade-offs as ADRs.

## Secrets and local artifacts

- `scripts/config.json` is generated locally and may contain Discord or Telegram
  credentials. It is ignored by Git; never display, copy, or commit its secrets.
- `.env*`, runtime state, logs, local videos, `.claude/`, and Obsidian workspace or
  plugin state are intentionally ignored.
- `.claude/settings.local.json` is historical input only. Its broad command
  allowlist is not a Codex permission policy and must not be copied into Codex
  configuration.
- For new audio or video transcription on this machine, use the global
  `$local-whisper` skill and the existing local service. Do not recreate the old
  Claude scratchpad or install another Whisper stack unless explicitly asked.

## Python workflow and validation

- Supported baseline: Python 3.10+ with `requests` and `beautifulsoup4`.
- Prefer small, testable changes and retain explicit timeouts, bounded polling,
  and graceful public-data failure handling.
- For documentation or configuration changes, run:
  - `python -m compileall -q scripts`
  - a TOML parse check for `.codex/config.toml`
  - `git diff --check`
- For script changes, also run the affected CLI's `--help` and the smallest safe
  targeted test. Network smoke tests should be limited to the changed data path
  and should record the source and date checked.
- Do not run live polling loops, send notifications, or create runtime state as a
  generic validation step.

## Git and external writes

- Preserve unrelated user changes and inspect the diff before committing.
- This repository currently has no Git remote. Do not infer a GitHub destination.
- Creating or modifying GitHub issues, PRs, labels, or remotes is an external
  write and requires an explicit user request.

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues using the `gh` CLI. See
`docs/agents/issue-tracker.md`.

### Triage labels

The five default canonical triage labels are used without overrides. See
`docs/agents/triage-labels.md`.

### Domain docs

This project uses the single-context domain-documentation layout. See
`docs/agents/domain.md`.
