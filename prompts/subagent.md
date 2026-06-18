# Subagent — When to Delegate

Subagents protect the main context from exploration noise and parallelize
independent work. They are **not free** — each spawn re-derives context cold. Use
only when the win is real.

## Use a subagent for

- **Broad code search** spanning >3 files or unknown locations.
- **Independent parallel work** — two queries with no dependency between them. Spawn both, await both.
- **Bounded research** with a written deliverable (`< 200 words`) so the raw output never enters the parent context.
- **Risky reads of large files** you only need a summary of.

## Do NOT use a subagent for

- Tasks where you already know the target file/symbol — read it directly.
- Writing/refactoring code on shared files — keep that in the parent so the diff is coherent.
- Long-running chains of dependent steps — each spawn pays cold-start cost. Run sequentially in-parent.
- "Just in case it parallelizes" — if you can't name what makes the work independent, it isn't.

## How to brief one

- State the goal in one paragraph (what + why).
- List what you already ruled out — saves rework.
- Specify the deliverable shape (`bulleted list`, `< 200 words`, `file:line citations`).
- Never delegate _understanding_ — don't write "based on findings, fix the bug." Synthesize yourself.

## Verifying

A subagent reports what it _intended_ to do, not necessarily what happened. If it wrote code: read the diff. If it claimed a file exists: grep it. Trust the artifact, not the summary.

## Token budget

Subagent output crosses back into the parent context. Cap the deliverable size in the brief. A 5K-token summary defeats the purpose.

## Model tier routing

Cheaper models for cheaper jobs. Codex task delegation can inherit the parent
model or use an explicit model override when the task justifies it. Do not
override by habit.

| Tier                  | Use for                                                                                                                                                                         | Don't use for                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **Mini**              | File search, "where is X defined", list extraction, summarizing long output, log triage                                                                                         | Architectural choices, hard debugging, anything risk-graded MED+ by `prompts/risk-review.md` |
| **Inherited/default** | Standard coding, test writing, straightforward refactor, code review of small diffs, normal `prompts/grill-me.md`                                                               | Tiny lookups, or genuinely deep architecture work                                            |
| **Frontier**          | Architecture decisions, risky changes (`prompts/risk-review.md` ≥2 HIGH), ADR drafting, hard debugging where the default model stalled, multi-file logic with subtle invariants | Anything the mini tier could do                                                              |

### Rules of thumb

- Inherit the parent model by default. Drop to mini only when the task is
  obviously bounded and shape-clear.
- Promote to frontier when `prompts/risk-review.md` flags ≥2 HIGH dimensions,
  the default model has tried and failed twice, or you're about to write an ADR.
- For independent parallel work: route each spawn to its own tier only when that
  materially improves cost or quality.
