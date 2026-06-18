# Assess Capabilities — acquire the right skills, MCP servers & plugins before building

Use at **project kickoff** (describe the project) or **before any non-trivial
feature** (describe the feature). Goal: pull in the capabilities that genuinely
help — across all three layers — skip everything the base already covers, keep it lean.

## Input

A description of the project, or the feature about to be built.

## Steps

1. **Identify needs** — list the concrete domains/tasks and the **stack** involved
   (e.g. Vercel/Next.js, Docker, Stripe, Supabase, Sentry, AWS, Postgres, Figma).
2. **Check what the base already covers — do NOT re-add these:**
   - Skills/prompts: grill-me, tdd, diagnose, zoom-out, security-scan, preflight, to-issues
   - MCP servers: **github, filesystem, git, playwright, sequential-thinking, context7** are already configured
   - CodeGraph: available when `codegraph` is installed and `.codegraph/` exists; do not assume it is configured everywhere
   - Plugins: none are installed by the base harness; use project-local MCP/skills first
   - Workflow: Codex subagents are available through tool discovery when explicitly requested
3. **For genuine gaps, assess all three layers:**
   - **Skill?** Invoke `find-skills` / `npx skills find "<need>"`; check official/vendor sources first.
   - **MCP server?** Many stacks have one (Vercel, Docker, Stripe, Supabase, Sentry, Linear, Notion, Figma…). Prefer official MCP servers or mature community servers.
   - **Plugin?** Use `tool_search` first when a plugin/tool may already be available; install only exact matches for the user's request.
4. **Vet before installing** — prefer official/vendor sources, 1K+ installs, repo >100 stars, and low context cost. Reject paid-API/niche unless clearly needed.
5. **Install only high-value, non-redundant capabilities**, project-scoped. Keep skills well under ~10; remember MCP servers can be token-heavy too.
6. **Report, then build** — state what you added per layer (and why), what you skipped (already covered), then proceed.

## Guardrails

- Prefer ONE plugin that bundles a stack over many loose skills, when available.
- A base-harness prompt beats a new skill when they overlap; an existing MCP beats a new one.
- Never install unvetted. This is an assessment, not a shopping spree — if the base covers it, add nothing.
