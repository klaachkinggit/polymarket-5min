# Applying This Harness

> **For AI agents:** the user told you to use this harness. Follow these steps exactly — don't skip, don't improvise.

## Apply (from the project root)
```bash
# TOOL = claude | codex | all   (this harness targets Claude Code + Codex)
TOOL=<your-tool> bash <(curl -fsSL https://raw.githubusercontent.com/klaachkinggit/klaach_harness/main/apply.sh)
```
Tool not listed → `TOOL=all`, then read [HARNESS.md](HARNESS.md) to finish wiring it up.

No curl? Clone outside the project, run the installer from the project root, then remove the clone:
```bash
gh repo clone klaachkinggit/klaach_harness /tmp/klaach_harness
TOOL=<your-tool> HARNESS_RAW_BASE=file:///tmp/klaach_harness bash /tmp/klaach_harness/apply.sh
rm -rf /tmp/klaach_harness
```
Do not leave a `klaach_harness/` folder inside the project.

## What gets applied
| Component | Where | Who reads it |
|-----------|-------|-------------|
| Rules | per-tool file (see HARNESS.md) | your tool, auto-loaded |
| MCP config | per-tool via `gen-mcp.py` (`.mcp.json` Claude / `.codex/config.toml` Codex) | your tool |
| Prompts | `prompts/` | any tool (paste) |
| Git hooks + CI | `.githooks/`, `.github/workflows/ci.yml` | git / GitHub — any tool or human |
| Slash commands | `.claude/commands/` | Claude Code |
| Runtime hooks | `.claude/hooks/` + `.claude/settings.json` (Claude) / `.codex/hooks/` + `.codex/hooks.json` (Codex) | Claude Code, Codex |
| Skills | `.claude/skills/` + `.codex/skills/` (mirrored find-skills + front-end design set) | Claude Code, Codex |
| Code graph | CodeGraph — `codegraph init` when installed; machine-level MCP wiring is opt-in with `INSTALL_CODEGRAPH_MCP=1` | Claude Code, Codex (MCP when wired) |

## After applying — VERIFY (don't skip)
Setup can fail partially (missing token, network, CLI mismatch). `apply.sh` prints a `⚠️ FAILED` block if so — read it. Then:
1. **Git hooks:** `git config --get core.hooksPath` → `.githooks`
2. **MCP** (Claude Code): `claude mcp list` → `github`, `filesystem`, `git`, `playwright`, `sequential-thinking`, `context7` listed. Empty = re-run after setting `GITHUB_TOKEN`.
3. **Runtime hooks:** `ls .claude/hooks/` and/or `ls .codex/hooks/` → 6 `.sh` files for each enabled provider. Codex: also verify a known-bad command is blocked — see HARNESS.md caveat.
4. **Env:** copy `.env.example` → `.env`, set `GITHUB_TOKEN` (+ `DATABASE_URL` if Postgres).
5. **Overwrites:** existing config was backed up to `<file>.bak` — merge anything you need.
6. **Context:** `tools/check-agent-context.sh --tool all` → confirms the selected agent can see rules, skills, hooks, and MCP config.
7. **Preflight:** `tools/preflight-harness.sh` → blocking local check for the applied harness.

Then add project-specific rules at the bottom of your rules file (below `<!-- Add project-specific rules below this line -->`):
```markdown
## Project: my-app
- Stack / Test command / Lint command / Deploy / constraints
```

## Before building
Per the rules, before a non-trivial feature run `assess-capabilities` (or ask *"what skills/MCP/plugins does this need?"*) — it pulls the right capabilities and skips what the base already covers. See PROFILES.md.
For large/ambiguous work, use `sequential-thinking`. For version-sensitive library, SDK, framework, or API behavior, use `context7` before relying on memory.
