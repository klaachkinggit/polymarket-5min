# Cost Review — Token / Spend Sanity Check

Run at session end (or weekly for long-running projects). The harness can't instrument LLM tokens at the hook layer — this prompt is the manual checkpoint.

## What to look at

- Provider dashboard for the day's spend.
- **Repo signals:**
  - `.codex/bash.log` size and command count (proxy for tool-call density).
  - `.claude/bash.log` size and command count when working in Claude Code.
  - Long-running subagent spawns — each pays cold-start.

## Diagnose if cost feels high

1. **Skill bloat** — inspect the provider-local mirror (`.codex/skills/` in Codex, `.claude/skills/` in Claude) and the active skill list. Every skill description loads each session. Prune anything unused for ~2 weeks, then mirror the curated set.
2. **MCP server count** — inspect `.codex/config.toml` and Claude MCP settings if present. Each server's tool list is in-context. Disable per-project servers you're not using.
3. **Subagent over-use** — Did you spawn agents for tasks you could've read directly? See `prompts/subagent.md`.
4. **No compaction** — Long sessions without compaction repeatedly re-read history. `AGENTS.md` says compact at phase boundaries.
5. **Subagent tiering** — Were spawns routed to the right model? Mini for cheap lookups, inherited/default for normal work, frontier only for `prompts/risk-review.md` ≥2 HIGH or ADR-worthy work. See `prompts/subagent.md`.

## Output

A 3-line note in `MEMORY.md` if a structural change is needed (e.g., "skill X removed — cost spike from descriptions"). Otherwise no action.
