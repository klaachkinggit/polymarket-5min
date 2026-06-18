# SPARC — Five-Phase Build

Structured methodology for non-trivial features. Each phase has a hard gate — do not advance until met. Pairs with `grill-me` (before phase 1) and `preflight` (before merge).

## S — Specification
- What problem, for whom, with what acceptance criteria.
- Out-of-scope list (at least 3 items you're deliberately not doing).
- **Gate:** can you write the test names from the spec? If not, go back.

## P — Pseudocode
- Plain-language algorithm. No syntax. Name the data shapes.
- Identify the 1–3 risky steps (concurrency, ordering, partial failure).
- **Gate:** for each risky step, written a failure mode + recovery plan?

## A — Architecture
- Where it lives (files/modules), what it depends on, what depends on it.
- New external surface: API/CLI/config? List it.
- If the choice is hard to reverse → write an ADR (`prompts/adr.md`).
- **Gate:** can a reviewer name the blast radius from this section alone?

## R — Refinement (TDD)
- RED → GREEN → REFACTOR per `prompts/tdd.md`.
- Smallest test that proves the next slice. Implement until green. Then refactor.
- **Gate:** no `TODO`, no commented-out code, no skipped tests in the diff.

## C — Completion
- Run `prompts/preflight.md` end to end.
- If auth/data/infra changed: run `prompts/security-scan.md`.
- Update `MEMORY.md` if a non-obvious decision was made (`prompts/memorize.md`).
- **Gate:** all preflight items PASS; ADR (if any) is `Accepted`.

## When to skip
SPARC has overhead. Skip for: typo fixes, single-line bug fixes, dependency bumps, formatting. Use whenever the change spans >1 file and changes behavior.
