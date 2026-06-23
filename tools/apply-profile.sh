#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  tools/apply-profile.sh <profile> [--tool claude|codex|all] [--dry-run]

Profiles:
  vercel    Adds Vercel hosted MCP: https://mcp.vercel.com
  supabase  Adds Supabase hosted MCP in read-only mode
  stripe    Adds Stripe local MCP via npx, forwarding STRIPE_SECRET_KEY
  figma     Adds Figma hosted MCP: https://mcp.figma.com/mcp
  ponytail  Adds the ponytail npm package to package.json
  all       Adds all MCP profiles above

Supabase environment knobs:
  SUPABASE_PROJECT_REF   Adds project_ref=<id> to the hosted MCP URL
  SUPABASE_MCP_FEATURES  Adds features=<groups> to the hosted MCP URL

Writes only project-local config:
  Claude: .mcp.json
  Codex:  .codex/config.toml
  Package profiles: package.json

Use --dry-run to print the config that would be written without changing files.
EOF
}

PROFILE=""
TOOL="all"
DRY_RUN=0

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
    --dry-run)
      DRY_RUN=1
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

if [ -z "$PROFILE" ]; then
  usage >&2
  exit 2
fi

case "$TOOL" in
  claude|codex|all) ;;
  *)
    echo "--tool must be claude, codex, or all" >&2
    exit 2
    ;;
esac

PROFILE="$PROFILE" TOOL="$TOOL" DRY_RUN="$DRY_RUN" python3 - <<'PY'
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode


def supabase_url():
    query = {"read_only": "true"}
    if os.environ.get("SUPABASE_PROJECT_REF"):
        query["project_ref"] = os.environ["SUPABASE_PROJECT_REF"]
    if os.environ.get("SUPABASE_MCP_FEATURES"):
        query["features"] = os.environ["SUPABASE_MCP_FEATURES"]
    return "https://mcp.supabase.com/mcp?" + urlencode(query)


def server_defs():
    return {
        "vercel": {
            "claude": {"type": "http", "url": "https://mcp.vercel.com"},
            "codex": {"url": "https://mcp.vercel.com"},
        },
        "supabase": {
            "claude": {"type": "http", "url": supabase_url()},
            "codex": {"url": supabase_url()},
        },
        "stripe": {
            "claude": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@stripe/mcp@latest"],
                "env": {"STRIPE_SECRET_KEY": "$STRIPE_SECRET_KEY"},
            },
            "codex": {
                "command": "npx",
                "args": ["-y", "@stripe/mcp@latest"],
                "env_vars": ["STRIPE_SECRET_KEY"],
            },
        },
        "figma": {
            "claude": {"type": "http", "url": "https://mcp.figma.com/mcp"},
            "codex": {"url": "https://mcp.figma.com/mcp"},
        },
    }


def package_defs():
    return {
        "ponytail": {"dependency": "ponytail", "version": "^1.0.57"},
    }


PROFILE = os.environ["PROFILE"].lower()
TOOL = os.environ["TOOL"].lower()
DRY_RUN = os.environ["DRY_RUN"] == "1"
MCP_PROFILES = server_defs()
PACKAGE_PROFILES = package_defs()

if PROFILE == "all":
    mcp_names = list(MCP_PROFILES)
    package_names = []
elif PROFILE in MCP_PROFILES:
    mcp_names = [PROFILE]
    package_names = []
elif PROFILE in PACKAGE_PROFILES:
    mcp_names = []
    package_names = [PROFILE]
else:
    print("unknown profile: %s" % PROFILE, file=sys.stderr)
    known = list(MCP_PROFILES) + list(PACKAGE_PROFILES)
    print("known profiles: %s, all" % ", ".join(known), file=sys.stderr)
    sys.exit(2)


def write_claude(selected):
    path = Path(".mcp.json")
    cfg = {}
    if path.exists() and path.read_text().strip():
        try:
            cfg = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(".mcp.json is not valid JSON: %s" % exc)
    cfg.setdefault("mcpServers", {})
    for name in selected:
        cfg["mcpServers"][name] = MCP_PROFILES[name]["claude"]
    if DRY_RUN:
        print("DRY RUN .mcp.json (%s)" % ", ".join(selected))
        print(json.dumps(cfg, indent=2))
        return
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("  wrote .mcp.json (%s)" % ", ".join(selected))


def without_codex_servers(text, names):
    kept = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = re.match(r"\[mcp_servers\.([^\]]+)\]", lines[i])
        if match and match.group(1) in names:
            i += 1
            while i < len(lines) and not lines[i].startswith("["):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    return "\n".join(kept).rstrip()


def toml_value(value):
    return json.dumps(value)


def codex_block(name, entry):
    lines = ["[mcp_servers.%s]" % name]
    if "url" in entry:
        lines.append("url = %s" % toml_value(entry["url"]))
    else:
        lines.append("command = %s" % toml_value(entry["command"]))
        lines.append("args = %s" % toml_value(entry["args"]))
        if entry.get("env_vars"):
            lines.append("env_vars = %s" % toml_value(entry["env_vars"]))
    return "\n".join(lines)


def write_codex(selected):
    path = Path(".codex/config.toml")
    existing = path.read_text() if path.exists() else ""
    base = without_codex_servers(existing, set(selected))
    blocks = [codex_block(name, MCP_PROFILES[name]["codex"]) for name in selected]
    body = ("\n\n".join(part for part in [base, "\n\n".join(blocks)] if part.strip())).rstrip()
    if DRY_RUN:
        print("DRY RUN .codex/config.toml (%s)" % ", ".join(selected))
        print(body)
        return
    path.parent.mkdir(exist_ok=True)
    path.write_text(body + "\n")
    print("  wrote .codex/config.toml (%s)" % ", ".join(selected))


def write_package(selected):
    path = Path("package.json")
    if not path.exists():
        raise SystemExit("package.json missing; create one before applying package profile: %s" % ", ".join(selected))
    try:
        pkg = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit("package.json is not valid JSON: %s" % exc)
    deps = pkg.setdefault("dependencies", {})
    for name in selected:
        entry = PACKAGE_PROFILES[name]
        deps[entry["dependency"]] = entry["version"]
    if DRY_RUN:
        print("DRY RUN package.json (%s)" % ", ".join(selected))
        print(json.dumps(pkg, indent=2))
        return
    path.write_text(json.dumps(pkg, indent=2) + "\n")
    print("  wrote package.json (%s)" % ", ".join(selected))


if mcp_names and TOOL in ("claude", "all"):
    write_claude(mcp_names)
if mcp_names and TOOL in ("codex", "all"):
    write_codex(mcp_names)
if package_names:
    write_package(package_names)
PY
