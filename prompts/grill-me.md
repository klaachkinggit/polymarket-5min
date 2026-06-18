# Grill Me — Requirements Interview

Before writing any code for [TASK], conduct an exhaustive requirements interview.

Cover ALL categories — do not skip any:

1. **Scope** — What's in scope? What's explicitly out?
2. **Edge cases** — Failure modes? Empty/null/invalid input behavior?
3. **Dependencies** — What existing code does this touch? What breaks if this changes?
4. **Data flow** — Where does data come from? Where does it go? Who mutates it?
5. **Error handling** — What errors must be handled? What can bubble up?
6. **Testing** — Acceptance criteria? What needs a test?
7. **Performance** — Latency, memory, or throughput constraints?
8. **Security** — Auth checks? Input validation? Data exposure risk?
9. **Rollback** — If this breaks in prod, how do we recover?

Present ALL questions at once, grouped by category. Wait for answers. Write zero code until confirmed.
