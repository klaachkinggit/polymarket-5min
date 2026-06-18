# HARNESS.md — Capability Map (for agents)

> **AI agent told to use this repo as a harness? Read this.** It maps each layer
> to *your* tool's mechanism. Tool not listed → use the generic row and adapt.

## Mental model — layers
Universal layers work everywhere. Tool-specific layers: the *protection* is
universal, the *mechanism* differs. **Principle:** anything enforceable at the
git/CI layer is, so guarantees hold under any agent or human; runtime hooks are
a faster copy for tools that support them.

| Layer | Does | Universal? |
|-------|------|-----------|
| Rules | behavioral contract | ✅ content universal, filename per tool |
| Prompts | workflow templates | ✅ plain markdown |
| MCP | tool/data servers | ⚠️ same servers, config/path per tool |
| Git hooks + CI | block secrets, format, gate tests | ✅ any tool or human |
| Runtime hooks | block dangerous cmds/secrets mid-session | ❌ Claude Code + Codex only |
| Slash commands | prompts as `/commands` | ❌ Claude Code only; Codex uses `prompts/` directly |
| Optional plugins | curated packs | ❌ tool-specific, not base-loaded |

## Rules file — where your tool reads instructions
Same content (`RULES.md`, synced by `sync-rules.sh`); filename + MCP env-var syntax differ.

| Tool | File | MCP env-var syntax |
|------|------|--------------------|
| Claude Code | `CLAUDE.md` | `${VAR}` |
| Codex CLI | `AGENTS.md` | none — forward by name (`env_vars`) |
| Not listed? | copy `RULES.md` into your system prompt | check your docs |

> This harness targets **Claude Code + Codex**. Other tools should use `RULES.md`
> as their source; removed provider files are recoverable from git history.

## MCP — getting servers into your tool
`tools/gen-mcp.py` is the single source; it emits the right format/path:
```bash
python3 tools/gen-mcp.py claude    # → .mcp.json           (root)
python3 tools/gen-mcp.py codex     # → .codex/config.toml  (TOML)
```
Base servers: `github`, `filesystem`, `git` (`uvx mcp-server-git --repository .`), `playwright`, `sequential-thinking`, `context7`, `db` (if `DATABASE_URL` set). Agents should use `sequential-thinking` for complex planning/debugging and `context7` for version-sensitive library/API docs.
Tool not an emitter → translate `.mcp.json` (generic JSON) to your tool's format; adding an emitter is one function in `gen-mcp.py`. Stack-specific servers (Vercel, Supabase, Stripe, Figma) are project-local profiles: `tools/apply-profile.sh <name> [--tool claude|codex|all] [--dry-run]`, and removal is `tools/remove-profile.sh <name>`. Existing custom MCP servers are preserved. Discover other servers live via `registry.modelcontextprotocol.io` / awesome-mcp-servers / mcp.so / Smithery / PulseMCP. Don't re-add the base 5.

## Runtime hooks — Claude Code & Codex
Provider-local scripts read the tool-call as JSON on stdin and exit `2` to block.
- **Claude Code:** wired in `.claude/settings.json`, scripts in `.claude/hooks/`.
- **Codex:** wired in `.codex/hooks.json`, scripts in `.codex/hooks/`.
- **Verify:** run `tools/check-agent-context.sh --tool all` after applying, and test one known-bad outside path before trusting a new provider version.
- **Other tools (no hook system):** no runtime blocking — the git hooks cover the same ground at commit/push.

| Script | Blocks / does |
|--------|--------------|
| `project-scope.sh` | direct Read/Write/Edit paths outside the project root, common Bash path references outside the project root, symlink escapes, globs, `$HOME`, and uninspectable shell substitution; URLs stay allowed |
| `block-dangerous.sh` | recursive rm of root/home/cwd, `curl\|sh`, force-push main, fork bomb, mkfs, dd-to-disk; **+ rm/mv/truncate/read of `.env`/keys and `git clean -f`** (append `>>`, `cp` restore, and `.env.example` stay allowed) |
| `protect-secrets.sh` | read/write/edit of `.env`/`.pem`/`.key`/credentials via the file tools, including symlink aliases; **allows `*.example` templates** |
| `auto-format.sh` | prettier/black/ruff/gofmt/rustfmt on edited files |
| `log-bash.sh` | logs commands to provider-local logs (`.claude/bash.log`, `.codex/bash.log`) |
| `pre-pr-gate.sh` | blocks PR if tests fail |

## Git + CI — universal enforcement (every tool, every human)
- `.githooks/pre-commit` — block secrets, auto-format staged files.
- `.githooks/pre-push` — run tests, block on failure.
- `.github/workflows/ci.yml` — secret scan + lint + test on push/PR.
- Activate: `git config core.hooksPath .githooks` (apply.sh does it). Bypass once: `--no-verify`.

This is *why* the harness is model-agnostic on enforcement: the guarantees hold at git/CI regardless of which agent (or human) wrote the code.

## Code graph + token economy — CodeGraph
The single biggest token saver: a local, pre-indexed symbol/call/import graph that both Claude Code and Codex query over MCP instead of fanning out grep/read sweeps (~−47% tokens, −58% tool calls; 100% local, no embeddings API).
- **Install once (per machine):** `curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh`.
- **Per project:** `codegraph init` builds `.codegraph/` (gitignored) and auto-syncs on edits. `apply.sh` runs `codegraph init` if `codegraph` is on PATH. It only runs `codegraph install` when `INSTALL_CODEGRAPH_MCP=1` is set, because that wires machine-level MCP config.
- **Use it:** `codegraph_search` / `codegraph_explore` to find symbols, callers, and blast radius before reading files; `codegraph_status` to confirm sync. See the **Token economy** rules in `RULES.md`.

## Skills — lean on purpose
Descriptions load into context every session (past ~1% of the window they truncate + mis-activate). Base bundles `find-skills` (installs any other skill on demand) plus a **front-end set** for UI work — `frontend-design`, `ui-ux-pro-max`, `impeccable`, `web-design-guidelines`, `awesome-design-md`. Matt Pocock-style routines live as portable prompts (`grill-me`, `tdd`, `diagnose`, `zoom-out`, `to-issues`) instead of repo-vendored skill files. The base set is intentionally mirrored in `.claude/skills/` and `.codex/skills/`; keep both mirrors in sync. Everything else is per-project — see PROFILES.md, or ask *"find a skill for X"*. Prune skills unused for ~2 weeks.

Token discipline comes from the **lean-skills rule above**, `/compact` between work phases, `prompts/subagent.md`'s **model tier routing** (Haiku/Sonnet/Opus per task), YAGNI pressure in the base rules, and `/cost-review` — *not* from output-compression skills (see PROFILES.md "Don't install").

## Prompts
`prompts/*.md` — plain markdown, paste anywhere. Claude gets thin wrappers in `.claude/commands/`; Codex uses the shared project-local prompt bodies directly. List in README.

## Brand-new tool with none of these mechanisms?
Minimum viable adoption, in order:
1. Load `RULES.md` as system instructions. *(behavior)*
2. Translate `.mcp.json` to your MCP config. *(capabilities)*
3. Set `git config core.hooksPath .githooks`. *(enforcement — the safety net that needs no tool features)*
4. Use `prompts/*.md` as templates.

That's 80% of the value with zero tool-specific features.
