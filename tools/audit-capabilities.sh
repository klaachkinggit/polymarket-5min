#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

EXPECTED_PROFILES=()
CHECK_USER_RESOURCES=0

usage() {
  cat <<'EOF'
Usage:
  tools/audit-capabilities.sh [--expect-profile vercel|supabase|stripe|figma|ponytail|all] [--check-user-resources]

Checks:
  - Claude/Codex skill and hook mirrors
  - project-local MCP config syntax
  - duplicate Codex MCP sections
  - base MCP servers
  - expected optional MCP/package profiles
  - installed-project CI does not reference harness-only scripts
  - no user-level skills/resources left in ~/.codex, ~/.claude, or ~/.agents when --check-user-resources is set
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --expect-profile)
      EXPECTED_PROFILES+=("${2:-}")
      shift 2
      ;;
    --expect-profile=*)
      EXPECTED_PROFILES+=("${1#*=}")
      shift
      ;;
    --check-user-resources)
      CHECK_USER_RESOURCES=1
      shift
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ "${#EXPECTED_PROFILES[@]}" -eq 0 ]; then
  EXPECTED_PROFILES=()
fi

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

check_file AGENTS.md
check_file CLAUDE.md
check_file .mcp.json
check_file .codex/config.toml
check_file .codex/hooks.json
check_dir .claude/skills
check_dir .codex/skills
check_dir .claude/hooks
check_dir .codex/hooks

if [ -d klaach_harness ]; then
  fail "nested klaach_harness directory present"
else
  pass "no nested klaach_harness directory"
fi
if [ -d .harness-archive ]; then
  fail ".harness-archive directory present"
else
  pass "no .harness-archive directory"
fi

if python3 -m json.tool .codex/hooks.json >/dev/null 2>&1; then
  pass ".codex/hooks.json is valid JSON"
else
  fail ".codex/hooks.json is invalid JSON"
fi

if python3 -m json.tool .claude/settings.json >/dev/null 2>&1; then
  pass ".claude/settings.json is valid JSON"
else
  fail ".claude/settings.json is invalid JSON"
fi
if grep -q '"enabledPlugins"' .claude/settings.json .codex/hooks.json 2>/dev/null; then
  fail "base provider config contains enabledPlugins"
else
  pass "base provider config has no enabledPlugins"
fi

if python3 -m json.tool .mcp.json >/dev/null 2>&1; then
  pass ".mcp.json is valid JSON"
else
  fail ".mcp.json is invalid JSON"
fi

if diff -qr .claude/skills .codex/skills >/dev/null 2>&1; then
  pass "Claude/Codex skills mirrors match"
else
  fail "Claude/Codex skills mirrors differ"
fi

python3 - <<'PY'
from pathlib import Path
import sys

failures = []
for root in (Path(".claude/skills"), Path(".codex/skills")):
    for skill in sorted(root.glob("*/SKILL.md")):
        text = skill.read_text(errors="replace")
        if not text.startswith("---\n"):
            failures.append(f"{skill}: missing frontmatter")
            continue
        end = text.find("\n---", 4)
        if end == -1:
            failures.append(f"{skill}: unterminated frontmatter")
            continue
        frontmatter = text[4:end]
        if "\nname:" not in "\n" + frontmatter:
            failures.append(f"{skill}: missing name")
        if "\ndescription:" not in "\n" + frontmatter:
            failures.append(f"{skill}: missing description")

for failure in failures:
    print("FAIL " + failure)
sys.exit(1 if failures else 0)
PY
skill_status=$?
if [ "$skill_status" -eq 0 ]; then
  pass "skill frontmatter valid"
else
  failures=$((failures + 1))
fi

claude_hooks="$(find .claude/hooks -maxdepth 1 -type f -name '*.sh' -exec basename {} \; | sort)"
codex_hooks="$(find .codex/hooks -maxdepth 1 -type f -name '*.sh' -exec basename {} \; | sort)"
expected_hooks="$(printf '%s\n' auto-format.sh block-dangerous.sh log-bash.sh pre-pr-gate.sh project-scope.sh protect-secrets.sh | sort)"
if [ "$claude_hooks" = "$codex_hooks" ]; then
  pass "Claude/Codex hook sets match"
else
  fail "Claude/Codex hook sets differ"
fi
if [ "$claude_hooks" = "$expected_hooks" ]; then
  pass "expected provider hook set installed"
else
  fail "provider hook set does not match expected hooks"
fi
for hook in $expected_hooks; do
  if [ -x ".claude/hooks/$hook" ] && [ -x ".codex/hooks/$hook" ]; then
    pass "$hook executable in both providers"
  else
    fail "$hook is not executable in both providers"
  fi
done

expected_skills="$(printf '%s\n' awesome-design-md find-skills frontend-design impeccable ui-ux-pro-max web-design-guidelines | sort)"
claude_skills="$(find .claude/skills -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)"
codex_skills="$(find .codex/skills -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)"
if [ "$claude_skills" = "$expected_skills" ] && [ "$codex_skills" = "$expected_skills" ]; then
  pass "expected provider skill set installed"
else
  fail "provider skill set does not match expected skills"
fi
if grep -R --include='SKILL.md' -nE 'npx skills add .* -g|npx skills add .* --global' .claude/skills .codex/skills >/dev/null; then
  fail "skill instructions include global install guidance"
else
  pass "skill install guidance is project-local"
fi

if grep -q "sequential-thinking" AGENTS.md CLAUDE.md && grep -q "context7" AGENTS.md CLAUDE.md; then
  pass "agent rules mention sequential-thinking and context7"
else
  fail "agent rules must mention sequential-thinking and context7"
fi

prompt_names="$(find prompts -maxdepth 1 -type f -name '*.md' -exec basename {} \; | sort)"
command_names="$(find .claude/commands -maxdepth 1 -type f -name '*.md' -exec basename {} \; | sort)"
if [ "$prompt_names" = "$command_names" ]; then
  pass "Claude command wrappers match prompts"
else
  fail "Claude command wrappers do not match prompts"
fi

for script in tools/apply-profile.sh tools/remove-profile.sh tools/audit-capabilities.sh \
              tools/check-agent-context.sh tools/check-profile.sh tools/preflight-harness.sh \
              tools/update-harness.sh; do
  if bash -n "$script"; then
    pass "$script syntax"
  else
    fail "$script syntax"
  fi
done
if [ -f apply.sh ]; then
  if bash -n apply.sh; then
    pass "apply.sh syntax"
  else
    fail "apply.sh syntax"
  fi
fi
if [ -f tools/test-harness-integration.sh ]; then
  if bash -n tools/test-harness-integration.sh; then
    pass "tools/test-harness-integration.sh syntax"
  else
    fail "tools/test-harness-integration.sh syntax"
  fi
fi

if grep -R "tools/test-harness-integration.sh" .github/workflows >/dev/null 2>&1; then
  fail "installed CI references harness-only integration script"
else
  pass "installed CI avoids harness-only integration script"
fi

if python3 -m py_compile tools/gen-mcp.py >/dev/null 2>&1; then
  pass "tools/gen-mcp.py compiles"
else
  fail "tools/gen-mcp.py does not compile"
fi

python3 - "${EXPECTED_PROFILES[@]-}" <<'PY'
import json
import re
import sys
from pathlib import Path

failures = []
warnings = []
base = {"github", "filesystem", "git", "playwright", "sequential-thinking", "context7"}
mcp_profiles = set()
package_profiles = set()
for item in sys.argv[1:]:
    if item == "all":
        mcp_profiles.update(["vercel", "supabase", "stripe", "figma"])
    elif item == "ponytail":
        package_profiles.add(item)
    elif item:
        mcp_profiles.add(item)

try:
    claude = json.loads(Path(".mcp.json").read_text()).get("mcpServers", {})
except Exception as exc:
    failures.append("could not inspect .mcp.json: %s" % exc)
    claude = {}

codex_text = Path(".codex/config.toml").read_text() if Path(".codex/config.toml").exists() else ""
codex = re.findall(r"^\[mcp_servers\.([^\].]+)\]", codex_text, re.M)
codex_set = set(codex)

dupes = sorted(name for name in codex_set if codex.count(name) > 1)
if dupes:
    failures.append("duplicate Codex MCP sections: %s" % ", ".join(dupes))

for name in sorted(base):
    if name not in claude:
        failures.append("Claude base MCP missing: %s" % name)
    if name not in codex_set:
        failures.append("Codex base MCP missing: %s" % name)

if claude.get("git", {}).get("command") != "uvx":
    failures.append("Claude git MCP should use uvx")
if claude.get("github", {}).get("env", {}).get("GITHUB_PERSONAL_ACCESS_TOKEN") != "${GITHUB_TOKEN}":
    failures.append("Claude github MCP should map GITHUB_TOKEN to GITHUB_PERSONAL_ACCESS_TOKEN")
git_match = re.search(r"^\[mcp_servers\.git\]\n(?P<body>.*?)(?=^\[|\Z)", codex_text, re.M | re.S)
if not git_match or 'command = "uvx"' not in git_match.group("body"):
    failures.append("Codex git MCP should use uvx")
github_match = re.search(r"^\[mcp_servers\.github\.env\]\n(?P<body>.*?)(?=^\[|\Z)", codex_text, re.M | re.S)
if not github_match or 'GITHUB_PERSONAL_ACCESS_TOKEN = "$GITHUB_TOKEN"' not in github_match.group("body"):
    failures.append("Codex github MCP should map GITHUB_TOKEN to GITHUB_PERSONAL_ACCESS_TOKEN")

for name in sorted(mcp_profiles):
    if name not in {"vercel", "supabase", "stripe", "figma"}:
        failures.append("unknown expected profile: %s" % name)
        continue
    if name not in claude:
        failures.append("Claude profile MCP missing: %s" % name)
    if name not in codex_set:
        failures.append("Codex profile MCP missing: %s" % name)

if package_profiles:
    try:
        package = json.loads(Path("package.json").read_text())
    except Exception as exc:
        failures.append("could not inspect package.json for package profiles: %s" % exc)
        package = {}
    package_deps = {}
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        value = package.get(section)
        if isinstance(value, dict):
            package_deps.update(value)
    for name in sorted(package_profiles):
        if name != "ponytail":
            failures.append("unknown expected profile: %s" % name)
        elif "ponytail" not in package_deps:
            failures.append("package profile missing from package.json: ponytail")

for msg in failures:
    print("FAIL " + msg)
for msg in warnings:
    print("WARN " + msg)
sys.exit(1 if failures else 0)
PY
profile_status=$?
if [ "$profile_status" -eq 0 ]; then
  pass "MCP config contents"
else
  failures=$((failures + 1))
fi

if [ "$CHECK_USER_RESOURCES" = "1" ]; then
  USER_PATHS=(
    "$HOME/.codex/skills"
    "$HOME/.codex/plugins"
    "$HOME/.codex/vendor_imports"
    "$HOME/.claude/skills"
    "$HOME/.claude/commands"
    "$HOME/.claude/plugins/cache"
    "$HOME/.claude/plugins/marketplaces"
    "$HOME/.claude/plugins/data"
    "$HOME/.claude/plugins/installed_plugins.json"
    "$HOME/.agents"
  )

  for path in "${USER_PATHS[@]}"; do
    if [ -e "$path" ]; then
      fail "user-level resource still exists: $path"
    else
      pass "user-level resource absent: $path"
    fi
  done

  if find "$HOME/.codex" "$HOME/.claude" -path '*/SKILL.md' -print -quit 2>/dev/null | grep -q .; then
    fail "user-level SKILL.md found under ~/.codex or ~/.claude"
  else
    pass "no user-level SKILL.md under ~/.codex or ~/.claude"
  fi

  if [ -f "$HOME/.codex/config.toml" ] && grep -Eq '^\[(plugins|marketplaces)\.' "$HOME/.codex/config.toml" 2>/dev/null; then
    fail "Codex user config still has plugin/marketplace sections"
  else
    pass "Codex user config has no plugin/marketplace sections"
  fi
else
  pass "user-level resource check skipped"
fi

printf '\n'
if [ "$failures" -gt 0 ]; then
  printf 'Capability audit failed: %s failure(s), %s warning(s)\n' "$failures" "$warnings"
  exit 1
fi

printf 'Capability audit passed: %s warning(s)\n' "$warnings"
