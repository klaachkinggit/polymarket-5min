# Learn — End-of-Task Reflection

After a non-trivial task, write down what you learned. Different from `MEMORY.md`:

- **`MEMORY.md`** = state of the world (decisions, constraints, quirks)
- **`LESSONS.md`** = heuristics for next time (what worked, what didn't, *why*)

Both are tool-agnostic markdown. No daemon, no vector DB. The whole self-learning mechanism is: *read at session start, append when something non-obvious happens.*

## When to append

- A technique surprised you (faster, cleaner, or caught a bug you'd have missed).
- A technique failed and the failure mode is worth remembering.
- A pattern recurred 3+ times this week.
- A skill / MCP / plugin proved its weight (or didn't).

## When NOT to append

- "I learned how to use git rebase" — already documented elsewhere.
- "X is hard" without a heuristic for next time.
- Anything ego-driven ("I'm great at Y"). Stick to actionable patterns.

## Format

Append-only. One entry per lesson.

```
## YYYY-MM-DD — short title  [category]
- **Saw:** what happened (one line).
- **Why:** the underlying reason it worked / failed.
- **Next time:** the heuristic (the part future-you will actually re-read).
```

Categories: `workflow` · `debug` · `test` · `arch` · `tools` · `prompt` · `cost`.

## Procedure

1. At session start: read `LESSONS.md` (in addition to `MEMORY.md`).
2. End of a non-trivial task — ask yourself: *did anything surprise me?*
3. If yes and it's non-obvious — append one entry. Otherwise skip.
4. Quarterly: prune entries that turned out to be wrong; merge duplicates.

The whole file should stay readable in one screen of session-start context. If it exceeds ~50 entries, prune harder — old lessons are *worse* than no lessons.
