# Audit — Periodic Repo Health Check

Run weekly (or before a milestone). Reports a punch list, no auto-fixes. The fix happens in a follow-up PR so the audit and the change are reviewable separately.

## Checks

1. **Test gaps** — Files changed in the last 14 days with no corresponding test edit:
   `git log --since=14.days --name-only --pretty=format: | sort -u | grep -E '\.(ts|tsx|js|py|go|rs)$'`
   For each, confirm a sibling/test file was touched in the same window.

2. **Dead code** — Exports/functions with zero references in the repo.
   TS: `npx ts-prune` · Py: `vulture .` · Go: `staticcheck -checks U1000` · Rust: `cargo +nightly udeps`.

3. **Dependency drift** — Outdated or vulnerable deps.
   `npm outdated` / `pip list --outdated` / `cargo outdated`. `npm audit --audit-level=high`.

4. **TODO / FIXME age** — TODOs older than 90 days:
   `git grep -nE 'TODO|FIXME|HACK' | while read line; do file=${line%%:*}; git log -1 --format='%ar' -- "$file"; echo "$line"; done`

5. **Hot files** — Files with the highest churn (often = poor abstraction):
   `git log --since=90.days --name-only --pretty=format: | sort | uniq -c | sort -rn | head -20`

6. **CI red-streak** — Recently failing checks:
   `gh run list --limit 30 --json conclusion,workflowName | jq -r '.[] | select(.conclusion=="failure") | .workflowName' | sort | uniq -c`

## Output
A markdown report grouped by check. For each finding: file/line, age, suggested action. **Do not auto-fix.** Open issues with `prompts/to-issues.md` for follow-up work.
