#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  tools/remove-profile.sh <profile> [--tool claude|codex|all] [--dry-run]

Profiles:
  vercel    Removes the Vercel MCP profile
  supabase  Removes the Supabase MCP profile
  stripe    Removes the Stripe MCP profile
  figma     Removes the Figma MCP profile
  all       Removes all profiles above

Removes only project-local profile entries:
  Claude: .mcp.json
  Codex:  .codex/config.toml

Use --dry-run to print the config that would remain without changing files.
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

PROFILE = os.environ["PROFILE"].lower()
TOOL = os.environ["TOOL"].lower()
DRY_RUN = os.environ["DRY_RUN"] == "1"
KNOWN = ["vercel", "supabase", "stripe", "figma"]

if PROFILE == "all":
    names = KNOWN
elif PROFILE in KNOWN:
    names = [PROFILE]
else:
    print("unknown profile: %s" % PROFILE, file=sys.stderr)
    print("known profiles: %s, all" % ", ".join(KNOWN), file=sys.stderr)
    sys.exit(2)


def remove_claude(selected):
    path = Path(".mcp.json")
    cfg = {}
    if path.exists() and path.read_text().strip():
        try:
            cfg = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(".mcp.json is not valid JSON: %s" % exc)
    cfg.setdefault("mcpServers", {})
    for name in selected:
        cfg["mcpServers"].pop(name, None)
    if DRY_RUN:
        print("DRY RUN .mcp.json after removing %s" % ", ".join(selected))
        print(json.dumps(cfg, indent=2))
        return
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("  wrote .mcp.json (removed %s)" % ", ".join(selected))


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


def remove_codex(selected):
    path = Path(".codex/config.toml")
    existing = path.read_text() if path.exists() else ""
    body = without_codex_servers(existing, set(selected))
    if DRY_RUN:
        print("DRY RUN .codex/config.toml after removing %s" % ", ".join(selected))
        print(body)
        return
    path.parent.mkdir(exist_ok=True)
    path.write_text((body + "\n") if body else "")
    print("  wrote .codex/config.toml (removed %s)" % ", ".join(selected))


if TOOL in ("claude", "all"):
    remove_claude(names)
if TOOL in ("codex", "all"):
    remove_codex(names)
PY
