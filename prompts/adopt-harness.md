# Adopt Harness — bring an existing project under this harness + clean up

Use when applying this dual-provider harness to a project that was built
**without** it and may already carry legacy skills, command docs, hooks, or
rules. Goal: adopt one shared project harness with Codex and Claude provider
mirrors, remove dead weight, keep what's genuinely project-specific.

## Steps

1. **Inventory** what's already there — list it before touching anything:
   - `AGENTS.md`, `CLAUDE.md`, `prompts/`, `.mcp.json`, `skills-lock.json`
   - provider mirrors: `.codex/`, `.claude/`
   - legacy harness folders only if present (`.agents/`) so they can be removed
   - git hooks (`git config --get core.hooksPath`), CI workflows in `.github/`
2. **Apply the harness** — from the target project root, run `apply.sh` directly
   via curl or from a temp clone outside the project. Do not clone/leave
   `klaach_harness/` inside the project. Install the shared files plus both
   provider mirrors. Back up any overwritten file to `<file>.bak`.
3. **Audit each pre-existing skill / command** and classify:
   - **KEEP** — project-specific, useful, no harness equivalent.
   - **REDUNDANT** — duplicates a harness skill/prompt (e.g. a custom "debugger"
     vs `diagnose`, custom "commit gate" vs the git hooks). → remove.
   - **STALE / UNUSED** — unreferenced, outdated, or low quality. → remove.
   - **IMPROVABLE** — good idea, weak execution (200 lines of prose, vague
     description, no validators). → rewrite tighter: sharp description, add
     hard-stops/validators/scripts, cut prose.
4. **Propose the plan to the user BEFORE changing anything.** Show the keep /
   remove / merge / improve list. Removing skills is destructive — get explicit
   confirmation unless the user has already asked for the cleanup.
5. **On approval** — execute the plan. Reconcile rules: fold any
   project-specific rules into the bottom of `AGENTS.md` and mirror the same
   contract into `CLAUDE.md`. Never silently drop project rules.
6. **Verify** — run `tools/check-agent-context.sh --tool all` and
   `tools/preflight-harness.sh`. Shared prompts under `prompts/`, provider hooks under
   `.codex/hooks` and `.claude/hooks`, mirrored skills under `.codex/skills`
   and `.claude/skills`, no tracked `.agents/`, no in-repo harness archive
   folders, and a quick sanity run.

## Guardrails (harness rules apply)

- Destructive actions need confirmation unless already requested in the task.
- Prefer git history over archive folders for removed harness files. Do not keep
  harness archives in the repository tree.
- Never discard project-specific rules — migrate them.
- Duplicated provider entrypoints are intentional compatibility, not stale
  redundancy. Keep them in sync.
- Fewer, sharper skills beat many overlapping ones.
