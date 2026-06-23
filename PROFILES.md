# PROFILES.md — Per-Project Skill Packs

The base harness stays lean (under the ~8–12 skill ceiling where Claude's
skill-selection accuracy degrades). It ships **one** discovery skill —
`find-skills` — instead of bundling niche skills that would tax every session's
context whether you use them or not.

When you start a project, pull only the pack(s) that project needs. Use the
discovery skill or the direct install commands below.

## Capability matrix (what's in the base, where to extend)

| Capability | In base | Extend via |
|------------|---------|------------|
| Behavioral contract | `RULES.md` synced to every tool | edit `RULES.md` only; `./sync-rules.sh` |
| Enforcement (boundary) | `.githooks/`, `.github/workflows/ci.yml` | add jobs to CI |
| Runtime safety (Claude/Codex) | provider mirrors: `.claude/hooks/`, `.codex/hooks/` | add behavior-equivalent hooks to both mirrors |
| Skill discovery | `find-skills` | profiles below |
| Token discipline | Lean-skills rule (HARNESS.md:72), `/compact`, **model-tier routing in `prompts/subagent.md`** (Haiku/Sonnet/Opus), YAGNI rules, `/cost-review` | — (see "Don't install" below) |
| Subagent delegation | `prompts/subagent.md` — when to spawn + which model tier | — (model-agnostic guidance, no runtime) |
| Cross-session memory | `MEMORY.md` + `prompts/memorize.md` | append entries; archive quarterly |
| Self-learning (heuristics) | `LESSONS.md` + `prompts/learn.md` | append only non-obvious lessons with a usable "next time" rule |
| Architecture decisions | `docs/adr/` + `prompts/adr.md` + template | one ADR per hard-to-reverse choice |
| Methodology | portable prompts (`sparc`, `grill-me`, `tdd`, `diagnose`, `zoom-out`, `to-issues`) | optionally add one project-scoped workflow skill |
| Risk classification | `prompts/risk-review.md` (per-diff dimension scoring) | run before `/preflight` on auth/data/infra changes |
| Periodic checks | `prompts/audit.md` (manual / on cadence) | wire to scheduled CI if needed |
| MCP base | github, filesystem, git via `uvx mcp-server-git`, playwright, sequential-thinking, context7, db when `DATABASE_URL` is set | `tools/apply-profile.sh` for stack-specific MCPs |
| Plugins base | none | keep plugin installs explicit and project-scoped; do not install user-level resources from `apply.sh` |

## How this differs from `find-skills`
- **`find-skills` = discovery.** Live, ranked-by-installs search of the skills.sh
  registry. Use it to find *what exists* for a need.
- **This file = judgment.** What a leaderboard can't tell you: which skills
  **conflict** with the base, licensing/paid-API traps, and — most useful — the
  **"don't install" list** below. Curated, so it can go stale: treat it as a
  starting point, re-vet picks periodically, and prefer `find-skills` for current
  rankings.

## Don't install — the base already covers these
Adding these duplicates harness functionality and just taxes context. (Verified
against the r/ClaudeAI "best skills" thread + the harness's own layers.)

| If tempted to add… | Use instead (already in base) |
|--------------------|-------------------------------|
| a custom debug/root-cause skill (e.g. myclaude `dendrite`, `five-vitals`) | `diagnose`, `zoom-out` |
| a commit gate / secret scanner / formatter skill | the git hooks (`.githooks/`) + `security-scan` |
| an issue-creation / spec skill (Matt Pocock "QA Session") | `to-issues`, `grill-me` |
| output-only compression gimmicks | model-tier routing + `/compact` + terse base rules; don't add style-only compression layers |
| context-engineering kits | redundant unless the *project itself* builds LLM agents |
| self-mutating / auto-tuning meta-skills (e.g. one-skill-to-rule-them-all) | overlaps harness hooks/memory; thread warns auto-mutation regresses quietly |
| a second workflow skill alongside Superpowers | swap, don't stack (see "Project workflow") |

## How to add skills to a project

**Via the discovery skill (any tool that supports skills):**
Just ask your agent: *"find a skill for X"* / *"is there a skill for testing web apps?"*
The `find-skills` skill checks the [skills.sh](https://skills.sh) leaderboard and
`npx skills find`, then installs the best match.

**Direct install (CLI):**
```bash
npx skills add <owner/repo@skill> -y       # project-local
```

Quality bar before installing: prefer 1K+ installs, prefer official sources
(`vercel-labs`, `anthropics`, `microsoft`), treat <100-star repos skeptically.

When adding a base or project-local skill for both runtimes, mirror it under
both `.claude/skills/` and `.codex/skills/`. If only one tool needs it, keep it
provider-local and document why.

## Profiles

### Web / frontend
For projects with a browser UI.
| Skill | Source | Why |
|-------|--------|-----|
| webapp-testing | `anthropics/skills@webapp-testing` | Playwright-driven E2E: launch server, drive browser, screenshots, console logs |
| ui-ux-pro-max | `nextlevelbuilder/ui-ux-pro-max-skill` | Design systems, color/font/layout reasoning |
| vercel agent-skills | `vercel-labs/agent-skills` | React/Next.js best practices, 100+ a11y/perf/UX rules |
| frontend-design | `anthropics/skills@frontend-design` | Sets bold design direction before coding |
| awesome-design-skills | `bergside/awesome-design-skills` | 57 visual-style skills (Neumorphism, Flat, Skeuomorphic…), MIT — add only the *one* style you're building in, not all 57 |

> Note: the base already includes a **Playwright MCP** server. `webapp-testing`
> is a workflow layer on top — add it only if MCP-level browser control isn't enough.

### Animation (subset of web)
| Skill | Source | Why |
|-------|--------|-----|
| gsap | `greensock/gsap-skills` | Correct GSAP/ScrollTrigger patterns — only if the project uses GSAP |

### Reporting / documents
For projects that generate files.
| Skill | Source | Why |
|-------|--------|-----|
| pdf | `anthropics/skills@pdf` | Generate/edit PDFs |
| xlsx | `anthropics/skills@xlsx` | Spreadsheets with formulas |
| docx | `anthropics/skills@docx` | Word docs with tracked changes |
| pptx | `anthropics/skills@pptx` | Presentations |

> License note: Anthropic's document skills are source-available, **not Apache-2.0**.
> Review the license before redistributing them inside a project.

### Data / scraping
For projects that ingest web data.
| Skill | Source | Why |
|-------|--------|-----|
| scrapegraph | `ScrapeGraphAI/just-scrape` | AI structured web extraction — needs a paid ScrapeGraph API key |

### AI / agent development
For projects that themselves build LLM agents.
| Skill | Source | Why |
|-------|--------|-----|
| skill-creator | `anthropics/skills@skill-creator` | Scaffold new skills |
| mcp-builder | `anthropics/skills@mcp-builder` | Build MCP servers |
| context-engineering | `muratcankoylan/Agent-Skills-for-Context-Engineering` | Context/prompt patterns (redundant with this harness for non-agent projects) |

## MCP servers by stack

Skills teach *how*; MCP servers connect to *external systems* (deploys, DBs,
error monitors, payments). Add the server for a stack your project actually uses.

**Already in the base — don't re-add:** `github`, `filesystem`, `git` via `uvx mcp-server-git`,
`playwright`, `sequential-thinking`, `context7`; `db` only when `DATABASE_URL` is set (Postgres via `@bytebase/dbhub`).

Apply the curated project-local MCP profiles:

```bash
tools/apply-profile.sh vercel
tools/apply-profile.sh supabase
tools/apply-profile.sh stripe
tools/apply-profile.sh figma
tools/apply-profile.sh ponytail
tools/apply-profile.sh all --dry-run
tools/audit-capabilities.sh --expect-profile all
tools/check-profile.sh all
```

Remove a profile cleanly:

```bash
tools/remove-profile.sh stripe
tools/remove-profile.sh ponytail
tools/remove-profile.sh all --dry-run
```

Both profile tools support `--tool claude|codex|all`. They are safe for existing
projects: generated base/profile entries are replaced or removed, while custom
MCP servers already present in `.mcp.json` or `.codex/config.toml` are preserved.

Package profiles are provider-neutral and work for Claude Code and Codex because
both agents see the same project files:

| Profile | What it changes | Notes |
|---------|-----------------|-------|
| Ponytail | Adds `ponytail@^1.0.57` to `package.json` dependencies | Published npm package, ISC license, no CLI or MCP server. Requires an existing `package.json`; run package-manager install after applying when you want lockfiles updated. |

Profile auth notes:

| Profile | Auth / scoping |
|---------|----------------|
| Vercel | Remote MCP at `https://mcp.vercel.com`; the client handles OAuth in-browser when the server is added or first used. |
| Supabase | Remote MCP at `https://mcp.supabase.com/mcp`; the harness defaults to `read_only=true`. Set `SUPABASE_PROJECT_REF=<id>` before applying to scope tools to one project, and `SUPABASE_MCP_FEATURES=database,docs` to limit tool groups. |
| Stripe | Local MCP via `npx -y @stripe/mcp@latest`; set `STRIPE_SECRET_KEY` in the shell or project env before use. Keep human confirmation enabled for write-capable tools. |
| Figma | Remote MCP at `https://mcp.figma.com/mcp`; use a Figma account with access to the file and paste a file/node link into the agent prompt. Full or Dev seats have the broadest MCP access. |

| Stack | Server (verified) | Install / endpoint | Official? |
|-------|-------------------|--------------------|-----------|
| Vercel | Vercel MCP | `tools/apply-profile.sh vercel` → `https://mcp.vercel.com` (OAuth) | ✅ |
| Docker | Docker Hub MCP + MCP Toolkit | `docker mcp` CLI / [hub.docker.com/mcp](https://hub.docker.com/mcp) | ✅ |
| Stripe | Stripe MCP | `tools/apply-profile.sh stripe` → `npx -y @stripe/mcp@latest` with `STRIPE_SECRET_KEY` forwarded | ✅ |
| Supabase | Supabase MCP | `tools/apply-profile.sh supabase` → `https://mcp.supabase.com/mcp?read_only=true` | ✅ |
| Sentry | Sentry MCP | `https://mcp.sentry.dev` (OAuth) | ✅ |
| Cloudflare | cloudflare/mcp-server-cloudflare | `*.mcp.cloudflare.com/mcp` (per product) | ✅ |
| AWS | awslabs/mcp (suite) | per-server via `uvx`, see [awslabs.github.io/mcp](https://awslabs.github.io/mcp/) | ✅ |
| Notion | makenotion/notion-mcp-server | `https://mcp.notion.com/sse` (OAuth) | ✅ |
| Linear | Linear MCP | `https://mcp.linear.app/mcp` (OAuth) | ✅ |
| Jira/Confluence | Atlassian Rovo MCP | `https://mcp.atlassian.com/v1/mcp` (OAuth) | ✅ |
| Figma | Figma MCP | `tools/apply-profile.sh figma` → `https://mcp.figma.com/mcp` | ✅ |

Run `tools/check-profile.sh <profile|all>` after applying profiles. It verifies
project-local Claude/Codex config shape, Stripe `STRIPE_SECRET_KEY`, Supabase
`read_only=true`, and reminds you when hosted OAuth is still a client-side step.
Use `--strict-auth` when missing local credentials should fail the check.

> Postgres note: the old Anthropic `server-postgres` is **archived/deprecated**
> (had a SQL-injection case) — stick with the base's `@bytebase/dbhub`.

**Discover more (live):** official registry `registry.modelcontextprotocol.io` ·
[punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) ·
[mcp.so](https://mcp.so) · [Smithery](https://smithery.ai) · [PulseMCP](https://www.pulsemcp.com).

## Plugins by stack

A plugin bundles skills + commands + hooks + MCP for a whole stack — often the
leanest way to equip a project (one install vs many loose skills).

Do not install plugins globally as part of the base harness. If a project needs a
plugin, install it intentionally for that project and keep Claude/Codex parity in
mind.

**Discovery:** run `/plugin` (Discover tab shows a **Context cost** estimate and
exactly what each will install) · web catalog [claude.com/plugins](https://claude.com/plugins).
The official marketplace `claude-plugins-official` is **auto-available**; the
community one needs `/plugin marketplace add anthropics/claude-plugins-community`.

| Need | Plugin | Install | Notes |
|------|--------|---------|-------|
| Vercel / Next.js | `vercel/vercel-plugin` | `npx plugins add vercel/vercel-plugin` | Official Vercel — 25 skills + 3 agents + 5 commands; auto-injects in Vercel/Next.js projects. **This is "the Vercel plugin."** |
| Pre-configured MCP (one-command) | `<name>@claude-plugins-official` | `/plugin install vercel@claude-plugins-official` | github, gitlab, vercel, firebase, supabase, sentry, linear, notion, figma, slack, asana, atlassian |
| Language intelligence (LSP) | `<lang>-lsp@claude-plugins-official` | `/plugin install typescript-lsp@claude-plugins-official` | ts, pyright, gopls, rust-analyzer, clangd, … — auto-diagnostics after edits |
| Version-correct library docs | Context7 MCP | already in base as `context7` | Injects version-specific docs (React/Next/Prisma/…); community |

**Base `apply.sh` plugin installs:** none. The base harness uses project-local
rules, prompts, hooks, skills, and MCP config.

## Project workflow — run exactly ONE

A "workflow" skill structures how the agent plans and implements. The base ships
portable prompts (`grill-me`, `sparc`, `tdd`, `diagnose`, `zoom-out`, `to-issues`).
If you add **Superpowers** for a project, keep it project-scoped and mirrored for
both tools. Do **not** run two workflow skills at once; they fight over the same
job. Swap, don't stack:

| Skill | Source | Fits |
|-------|--------|------|
| Superpowers | `obra/superpowers` | Small–medium, well-defined work; strong brainstorming → plan → execute |
| OpenSpec | `Fission-AI/OpenSpec` | Lightweight spec-driven build + rollback |
| GSD (Get-Shit-Done) | `gsd-build/get-shit-done` | Large, iterative projects; phased with heavy safety gates; `/gsd:map-codebase` onboarding |

Common pairing from the community: `grill-me` (pressure-test the idea) → workflow
skill (brainstorm → plan → implement). Both are compatible because grill-me is a
helper, not a workflow.

### Cross-runtime peer review (Claude + Codex)
You use both Claude Code and Codex — a community-endorsed pattern: have one build,
the other review. Different models catch different failure modes. No package needed;
just run `/review` (or paste the diff) in the *other* tool before merging.

## Skill hygiene (community-validated)
- One workflow skill at a time; small composable helpers around it.
- A skill's value is its **validators, hard-stops, and scripts** — not its prose.
  (This harness puts those at the git/CI layer so they hold under any tool.)
- Auto-updating skills is risky — a mutation can regress quietly. Keep stable skills frozen.
- Stale instruction files perform *worse* than none. Prune skills you haven't used in ~2 weeks.

## Rule of thumb

Audit every couple of weeks: for each installed skill, *did I use it?* If not,
remove it. Niche skills belong in the project that needs them — never in the base.
