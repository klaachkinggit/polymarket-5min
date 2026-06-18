# To Issues — Plan → GitHub Issues

Convert [PLAN/PRD] into GitHub issues.

Rules:
- **Vertical slices only** — each issue delivers end-to-end value (UI + API + DB + test). No horizontal slices.
- **One session per issue** — if it takes more than one focused session, split it.
- **Dependencies explicit** — "Blocked by #X" if relevant.

Issue format:
```
Title: [verb] [thing]   ← imperative, short

## Context
Why this exists.

## Acceptance criteria
- [ ] Specific, testable condition
- [ ] ...

## Out of scope
What this explicitly does NOT cover.
```

Output a numbered list ready to paste into GitHub. Confirm before creating issues via CLI.
