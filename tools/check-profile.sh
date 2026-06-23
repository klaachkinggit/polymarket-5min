#!/usr/bin/env bash
set -u

PROFILE=""
STRICT_AUTH=0

usage() {
  cat <<'EOF'
Usage:
  tools/check-profile.sh [vercel|supabase|stripe|figma|ponytail|all] [--strict-auth]

With no profile, checks optional profiles currently present in project-local
Claude/Codex MCP config and package.json. With a profile argument, that profile is expected.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --strict-auth)
      STRICT_AUTH=1
      shift
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [ -n "$PROFILE" ]; then
        echo "only one profile argument is supported" >&2
        usage >&2
        exit 2
      fi
      PROFILE="$1"
      shift
      ;;
  esac
done

PROFILE="$PROFILE" STRICT_AUTH="$STRICT_AUTH" python3 - <<'PY'
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

mcp_profiles = ["vercel", "supabase", "stripe", "figma"]
package_profiles = {"ponytail": "ponytail"}
known = mcp_profiles + list(package_profiles)
profile = os.environ.get("PROFILE", "").lower()
strict_auth = os.environ.get("STRICT_AUTH") == "1"
failures = []
warnings = []
checks = []

if profile and profile not in known + ["all"]:
    print("unknown profile: %s" % profile, file=sys.stderr)
    print("known profiles: %s, all" % ", ".join(known), file=sys.stderr)
    sys.exit(2)

try:
    claude = json.loads(Path(".mcp.json").read_text()).get("mcpServers", {})
except Exception:
    claude = {}

codex_text = Path(".codex/config.toml").read_text() if Path(".codex/config.toml").exists() else ""
codex = set(re.findall(r"^\[mcp_servers\.([^\].]+)\]", codex_text, re.M))
try:
    package = json.loads(Path("package.json").read_text()) if Path("package.json").exists() else {}
except Exception:
    package = {}

if profile == "all":
    expected_mcp = set(mcp_profiles)
    expected_packages = set()
elif profile:
    expected_mcp = {profile} if profile in mcp_profiles else set()
    expected_packages = {profile} if profile in package_profiles else set()
else:
    expected_mcp = {name for name in mcp_profiles if name in claude or name in codex}
    package_deps = {}
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        value = package.get(section)
        if isinstance(value, dict):
            package_deps.update(value)
    expected_packages = {name for name, dependency in package_profiles.items() if dependency in package_deps}

if not expected_mcp and not expected_packages:
    print("PASS no optional profiles installed")
    print("\nProfile check passed: 0 warning(s)")
    sys.exit(0)

for name in sorted(expected_mcp):
    if name not in claude:
        failures.append("Claude profile missing: %s" % name)
    if name not in codex:
        failures.append("Codex profile missing: %s" % name)

    entry = claude.get(name, {})
    if name == "stripe":
        env = entry.get("env", {})
        if "STRIPE_SECRET_KEY" not in env and "STRIPE_SECRET_KEY" not in os.environ:
            message = "Stripe profile needs STRIPE_SECRET_KEY in environment before use"
            if strict_auth:
                failures.append(message)
            else:
                warnings.append(message)
    elif name == "supabase":
        url = entry.get("url", "")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if query.get("read_only", [""])[0] != "true":
            failures.append("Supabase profile must be read_only=true")
        if "project_ref" not in query:
            warnings.append("Supabase profile has no project_ref; set SUPABASE_PROJECT_REF before applying when you want one project pinned")
    elif name == "vercel":
        checks.append("Vercel profile uses hosted OAuth MCP; run the client MCP auth flow if prompted")
    elif name == "figma":
        checks.append("Figma profile uses hosted OAuth MCP; run the client MCP auth flow if prompted")

for name in sorted(expected_mcp):
    print("PASS profile present in Claude and Codex config: %s" % name)

for name in sorted(expected_packages):
    dependency = package_profiles[name]
    installed = False
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        value = package.get(section)
        if isinstance(value, dict) and dependency in value:
            installed = True
    if installed:
        print("PASS package profile present in package.json: %s" % name)
    else:
        failures.append("package profile missing from package.json: %s" % name)

for item in checks:
    print("CHECK " + item)
for warning in warnings:
    print("WARN " + warning)
for failure in failures:
    print("FAIL " + failure)

print()
if failures:
    print("Profile check failed: %s failure(s), %s warning(s)" % (len(failures), len(warnings)))
    sys.exit(1)
print("Profile check passed: %s warning(s)" % len(warnings))
PY
