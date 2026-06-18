# TDD — RED-GREEN-REFACTOR

Implement [FEATURE] using strict RED-GREEN-REFACTOR. One cycle at a time.

**RED** — Write the failing test first.
- Test must fail for the right reason (missing impl, not import/syntax error)
- Run it. Confirm failure. Show output.
- Do NOT write implementation yet.

**GREEN** — Minimum code to pass the test.
- Simplest possible implementation — no cleanup, no abstractions yet
- Run test. Confirm green. Show output.

**REFACTOR** — Clean up with tests green.
- Remove duplication, improve naming, no new behavior
- Tests pass after every individual change

Do not skip RED. Do not write impl before seeing the test fail.
