# Risk Review — Diff Classifier

Score the current diff by risk dimension. Different from `code-review` (correctness/cleanups) and `preflight` (binary checklist) — this tells the reviewer *what to look hardest at*.

## Procedure

1. Run `git diff HEAD` (or `git diff <base>...HEAD` for a branch).
2. For each changed file, classify by the dimensions below.
3. Produce per-file scores + a top-3 hotspots list.

## Dimensions (score each LOW / MED / HIGH + one-line reason)

| Dim | What triggers HIGH |
|---|---|
| **Schema** | DB column add/drop, type change, index change, API contract field add/remove |
| **Auth/permissions** | Touches auth middleware, session handling, ACL, role checks, token logic |
| **Public API** | Exported function/CLI/HTTP signature changes; cross-service contract changes |
| **Concurrency** | New async, locks, transactions, queues, retries, idempotency assumptions |
| **Blast radius** | >5 callers affected, or a foundational module others import widely |
| **Reversibility** | One-way migration, deleted data, dropped column, deprecated endpoint |
| **State migration** | Existing rows/records need backfill or shape coercion |
| **External side effects** | New network call, file write, email/SMS, payment, third-party API |

## Output

```
RISK REVIEW
===========
Top hotspots (scrutinize first):
1. <file:line> — <dim>: <one-line why HIGH>
2. ...
3. ...

Per-file:
- <file>
    Schema:        LOW
    Auth:          LOW
    Public API:    MED — exported signature changed, called by 3 files
    Concurrency:   LOW
    Blast radius:  MED
    Reversibility: HIGH — drops `legacy_id` column, no backup path
    ...
```

## When to run

- Before `/preflight` on any change touching auth, data, or infra.
- Before merging a PR with >200 changed lines.
- When choosing a reviewer — hotspots tell you whose expertise you need.

If two or more dimensions land HIGH, the change is ADR-worthy — write one via `prompts/adr.md`.
