# Memorize — Cross-Session Memory

Tool-agnostic, file-based memory. Lives at `MEMORY.md` in the project root. Read at session start; append when a decision, constraint, or quirk would help a future session.

## What goes in
- **Decisions** that are not obvious from the code (why X over Y).
- **Constraints** the code can't express (regulatory, deadline, downstream contract).
- **Quirks** of the environment (this CI runner is slow; this MCP server flakes).
- **People/ownership** when it shapes review (X owns billing; ask before touching).

## What does NOT go in
- Anything derivable from `git log`, `git blame`, or the current code.
- Ephemeral task state — that belongs in the plan/todo for the current session.
- Secrets. Ever.

## Format
Append-only. One entry per change. Keep entries under ~150 chars; link out for detail.

```
## YYYY-MM-DD — short title
- Fact / decision / constraint.
- Why it matters (one line). Link: <PR / ADR / doc>.
```

## Procedure
1. At session start: read `MEMORY.md` if present.
2. When something memory-worthy surfaces: append the entry, do not edit prior ones.
3. If an entry becomes wrong, append a correction with the date — don't silently rewrite.
4. Quarterly: skim and archive stale entries to `MEMORY.archive.md`.
