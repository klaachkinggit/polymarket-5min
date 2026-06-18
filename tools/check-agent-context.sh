#!/usr/bin/env bash
set -u

ROOT="$(pwd)"
TOOL="all"

usage() {
  cat <<'EOF'
Usage:
  tools/check-agent-context.sh [--tool claude|codex|all]

Checks that the applied harness is visible to the selected provider from this
project root. This cannot inspect an already-running agent's context window;
restart the agent after applying if these files changed.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --tool)
      TOOL="${2:-}"
      shift 2
      ;;
    --tool=*)
      TOOL="${1#*=}"
      shift
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$TOOL" in
  claude|codex|all) ;;
  *)
    echo "--tool must be claude, codex, or all" >&2
    exit 2
    ;;
esac

failures=0
warnings=0

pass() { printf 'PASS %s\n' "$1"; }
fail() { printf 'FAIL %s\n' "$1"; failures=$((failures + 1)); }
warn() { printf 'WARN %s\n' "$1"; warnings=$((warnings + 1)); }

check_file() {
  if [ -f "$1" ]; then pass "$1 exists"; else fail "$1 missing"; fi
}

check_dir() {
  if [ -d "$1" ]; then pass "$1 exists"; else fail "$1 missing"; fi
}

check_text() {
  local file="$1" pattern="$2" label="$3"
  if [ -f "$file" ] && grep -q "$pattern" "$file"; then
    pass "$label"
  else
    fail "$label"
  fi
}

if [ -d "$ROOT/klaach_harness" ]; then
  fail "nested klaach_harness directory present; apply the harness, do not leave its repo inside this project"
else
  pass "no nested klaach_harness directory"
fi

if [ -d "$ROOT/.harness-archive" ]; then
  fail ".harness-archive present; use git history instead of in-repo archives"
else
  pass "no .harness-archive directory"
fi

for file in APPLY.md HARNESS.md PROFILES.md prompts/assess-capabilities.md prompts/sparc.md prompts/preflight.md; do
  check_file "$file"
done

check_text prompts/assess-capabilities.md "sequential-thinking" "assess-capabilities names sequential-thinking as base MCP"
check_text prompts/assess-capabilities.md "context7" "assess-capabilities names context7 as base MCP"

if [ "$TOOL" = "claude" ] || [ "$TOOL" = "all" ]; then
  check_file CLAUDE.md
  check_file .mcp.json
  check_file .claude/settings.json
  check_dir .claude/hooks
  check_dir .claude/skills
  check_dir .claude/commands
  check_text CLAUDE.md "sequential-thinking" "CLAUDE.md tells Claude to use sequential-thinking"
  check_text CLAUDE.md "context7" "CLAUDE.md tells Claude to use context7"
fi

if [ "$TOOL" = "codex" ] || [ "$TOOL" = "all" ]; then
  check_file AGENTS.md
  check_file .codex/config.toml
  check_file .codex/hooks.json
  check_dir .codex/hooks
  check_dir .codex/skills
  check_text AGENTS.md "sequential-thinking" "AGENTS.md tells Codex to use sequential-thinking"
  check_text AGENTS.md "context7" "AGENTS.md tells Codex to use context7"
fi

python3 - "$TOOL" <<'PY'
import json
import re
import sys
from pathlib import Path

tool = sys.argv[1]
failures = []
expected_skills = {
    "awesome-design-md",
    "find-skills",
    "frontend-design",
    "impeccable",
    "ui-ux-pro-max",
    "web-design-guidelines",
}
base_mcp = {"github", "filesystem", "git", "playwright", "sequential-thinking", "context7"}

def check_skills(root):
    path = Path(root)
    if not path.exists():
        return
    got = {item.name for item in path.iterdir() if item.is_dir()}
    missing = sorted(expected_skills - got)
    extra = sorted(got - expected_skills)
    if missing:
        failures.append("%s missing skills: %s" % (root, ", ".join(missing)))
    if extra:
        failures.append("%s has unexpected skills: %s" % (root, ", ".join(extra)))

if tool in ("claude", "all"):
    check_skills(".claude/skills")
    try:
        servers = set(json.loads(Path(".mcp.json").read_text()).get("mcpServers", {}))
        missing = sorted(base_mcp - servers)
        if missing:
            failures.append("Claude MCP missing: %s" % ", ".join(missing))
    except Exception as exc:
        failures.append("could not inspect .mcp.json: %s" % exc)

if tool in ("codex", "all"):
    check_skills(".codex/skills")
    text = Path(".codex/config.toml").read_text() if Path(".codex/config.toml").exists() else ""
    servers = set(re.findall(r"^\[mcp_servers\.([^\].]+)\]", text, re.M))
    missing = sorted(base_mcp - servers)
    if missing:
        failures.append("Codex MCP missing: %s" % ", ".join(missing))

for failure in failures:
    print("FAIL " + failure)
sys.exit(1 if failures else 0)
PY
status=$?
if [ "$status" -ne 0 ]; then
  failures=$((failures + 1))
else
  pass "provider skill and MCP surfaces present"
fi

printf '\n'
if [ "$failures" -gt 0 ]; then
  printf 'Agent context check failed: %s failure(s), %s warning(s)\n' "$failures" "$warnings"
  exit 1
fi

printf 'Agent context check passed: %s warning(s)\n' "$warnings"
