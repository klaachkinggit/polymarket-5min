# Diagnose — Structured Debugging

Debug [BUG/ERROR]. Follow this sequence — do not skip or reorder steps.

1. **REPRODUCE** — Get a reliable reproduction. Confirm bug exists now.
2. **MINIMIZE** — Smallest input/state that triggers it.
3. **HYPOTHESIZE** — List 3 possible causes ranked by likelihood. State assumptions explicitly.
4. **INSTRUMENT** — Add targeted logging/assertions to test top hypothesis. No guess-fixes.
5. **CONFIRM ROOT CAUSE** — Verify hypothesis before touching production code.
6. **FIX** — Minimal change. No refactoring while fixing.
7. **TEST** — Write a regression test that would have caught this. Confirm it passes.
8. **CLEAN UP** — Remove all debug instrumentation.

Report findings at each step before moving to the next.
