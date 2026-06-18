# ADR — Architecture Decision Record

Capture an architecturally significant decision so future-you and reviewers can recover the *why*. Use whenever a choice changes the shape of the system: data model, auth model, dependency swap, infra topology, build/test strategy, anything hard to reverse.

## When to write one
- Choice is hard to reverse or expensive to migrate.
- Reasonable engineers would disagree on the answer.
- Decision is load-bearing for other future decisions.
- Skip for: local refactors, lib version bumps, formatting.

## Procedure

1. Create `docs/adr/NNNN-kebab-title.md` (next free 4-digit number).
2. Fill from the template at `docs/adr/0000-template.md`.
3. Status starts `Proposed`. After review/merge → `Accepted`. If superseded, set `Status: Superseded by ADR-MMMM` on the old one and link from the new.
4. Reference the ADR from the PR description (`Closes ADR-NNNN`) so the decision and the code arrive together.

## Quality bar
- One decision per ADR.
- Context section answers *what forced this*; not a project intro.
- Alternatives section names at least 2 options seriously considered and *why rejected*. An ADR with no rejected alternatives is a confession, not a record.
- Consequences section lists both upsides and the costs you're accepting.
