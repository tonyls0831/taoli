## Linked issue and spec

<!-- PRs implement an already-triaged GitHub Issue; they are not raw feature requests. -->

- Issue:
- Durable spec / approved seam:

## What changed and why

<!-- Describe observable behavior and impact. For a fix, include the root cause. -->

## Public seam

<!-- Name the CLI/document interface exercised by callers and tests, or state “none”. -->

## Validation

- [ ] Smallest safe targeted test
- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m compileall -q scripts`
- [ ] Python 3.14 parses `.codex/config.toml`
- [ ] Affected CLI `--help` (if applicable)
- [ ] `git diff --check`
- [ ] Standards + Spec review completed

## Safety and external writes

- [ ] No secret, credential, local config, runtime state, log, or private media is included
- [ ] Human-execution boundary is preserved; no brokerage connection or automated order entry
- [ ] Validation did not send notifications, create schedules, or run an unbounded polling loop
- [ ] Every external write or bounded live read is linked to explicit owner authorization, or this PR performs none

## Known limitations

<!-- Record data-source, market-rule, capacity, execution, or maintenance limitations that remain. -->
