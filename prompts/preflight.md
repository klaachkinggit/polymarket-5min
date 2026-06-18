# Preflight — Pre-Ship Checklist

Run before every PR or deploy. Auto-detect test/lint/type commands from package.json, pyproject.toml, or Makefile. Report each item as PASS / FAIL / SKIP.

- [ ] **Tests** — All tests pass
- [ ] **Types** — Type check clean (tsc --noEmit, mypy, etc.)
- [ ] **Lint** — No errors (eslint, ruff, etc.)
- [ ] **Security** — Run security-scan on changed files (`git diff --name-only HEAD~1`) — no CRITICAL/HIGH
- [ ] **Debug artifacts** — None:
  `grep -rn "console\.log\|debugger\|breakpoint()\|pdb\|TODO\|FIXME\|HACK" $(git diff --name-only HEAD~1)`
- [ ] **Hardcoded secrets** — None:
  `grep -rE "(password|secret|token)\s*[:=]\s*['\"][^'\"]{6,}" $(git diff --name-only HEAD~1)`
- [ ] **Dependencies** — No new critical CVEs: `npm audit --audit-level=critical`
- [ ] **DB migrations** — Reversible? Tested against current schema?
- [ ] **Docs** — Public API changes reflected in docs/README?

Any FAIL blocks ship.
