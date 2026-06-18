#!/usr/bin/env bash
# Blocks PR creation if tests are failing.
# Matcher: mcp__github__create_pull_request
set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

run_tests() {
  echo "Running tests before PR..." >&2
  if ! "$@" 2>&1; then
    echo "BLOCKED: tests must pass before creating a PR." >&2
    exit 2
  fi
}

if [ -f package.json ]; then
  SCRIPT=$(python3 -c "
import json, sys
s = json.load(open('package.json')).get('scripts', {})
for name in ('test', 'test:unit', 'test:all'):
    t = s.get(name, '')
    if t and 'no test specified' not in t and t != 'exit 1':
        print(name)
        break
" 2>/dev/null || echo "")
  [ -n "$SCRIPT" ] && run_tests npm run "$SCRIPT"
elif [ -f pyproject.toml ] || [ -f pytest.ini ] || [ -f setup.cfg ]; then
  command -v pytest >/dev/null 2>&1 && run_tests pytest -q --tb=short
fi

exit 0
