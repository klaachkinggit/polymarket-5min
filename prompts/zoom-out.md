# Zoom Out — System Map

Before touching [AREA/FILE], build a system map. Do not make changes until map is confirmed.

1. **Entry points** — How does control/data enter this area? (routes, events, CLI commands)
2. **Dependencies** — What does this code import? What imports this code?
3. **Data shapes** — Key types, schemas, interfaces in play.
4. **Side effects** — What does this write to? (DB, files, network, events, cache)
5. **Test coverage** — What tests cover this? What's the gap?
6. **Recent changes** — `git log --oneline -20 -- <path>`
7. **Known issues** — TODOs, FIXMEs, warning comments in the area.

Output a concise map. Highlight anything surprising or risky.
