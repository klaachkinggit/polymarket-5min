#!/usr/bin/env bash
# Auto-format after Edit/Write. Graceful no-op if formatter not installed.
INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))
except Exception:
    pass
" 2>/dev/null)

{ [ -z "$FILE" ] || [ ! -f "$FILE" ]; } && exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
case "$FILE" in
  "$ROOT"/.codex/skills/*|"$ROOT"/.claude/skills/*|.codex/skills/*|.claude/skills/*) exit 0 ;;
esac
EXT="${FILE##*.}"

case "$EXT" in
  js|jsx|ts|tsx|css|scss|json|html|md|yaml|yml)
    # Try project-local prettier first, then global
    if [ -x "$ROOT/node_modules/.bin/prettier" ]; then
      "$ROOT/node_modules/.bin/prettier" --write "$FILE" 2>/dev/null || true
    elif command -v prettier >/dev/null 2>&1; then
      prettier --write "$FILE" 2>/dev/null || true
    fi
    ;;
  py)
    command -v ruff >/dev/null 2>&1 && ruff format "$FILE" --quiet 2>/dev/null || true
    command -v black >/dev/null 2>&1 && black "$FILE" --quiet 2>/dev/null || true
    ;;
  go)
    command -v gofmt >/dev/null 2>&1 && gofmt -w "$FILE" 2>/dev/null || true
    ;;
  rs)
    command -v rustfmt >/dev/null 2>&1 && rustfmt "$FILE" 2>/dev/null || true
    ;;
esac

exit 0
