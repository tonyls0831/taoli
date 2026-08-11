# Domain Docs

How the engineering skills should consume this project's domain documentation when exploring the codebase.

This project uses the **single-context** layout: one `CONTEXT.md` and one `docs/adr/` directory at the project root.

## Before exploring, read these

- **`CONTEXT.md`** at the project root.
- **`docs/adr/`** — read ADRs that touch the area about to be changed.

If either does not exist, **proceed silently**. Do not flag its absence or suggest creating it upfront. The `/domain-modeling` skill creates these files lazily when terminology or decisions are actually resolved.

## File structure

```text
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-example-decision.md
│   └── 0002-another-decision.md
└── src/
```

## Use the glossary's vocabulary

When output names a domain concept—in an issue title, refactor proposal, hypothesis, or test name—use the term defined in `CONTEXT.md`. Do not drift to synonyms the glossary explicitly avoids.

If a needed concept is absent from the glossary, reconsider whether the language belongs to the project or note the genuine gap for `/domain-modeling`.

## Flag ADR conflicts

If output contradicts an existing ADR, surface the conflict explicitly instead of silently overriding it:

> _Contradicts ADR-0007 (event-sourced orders)—but worth reopening because…_
