---
name: impeccable
description: Use for a final Codex-side UI quality audit before shipping frontend work. Checks for generic AI design tells, accessibility gaps, responsive issues, and product-fit problems.
---

# Impeccable

Use this skill after the UI is implemented and before final verification.

## Audit

Check the rendered UI and source against these failure modes:

- Generic SaaS composition: oversized hero cards, purple-blue gradients, decorative blobs, nested cards, and repetitive feature tiles.
- Weak product fit: visual style does not match the actual audience, workflow density, or domain.
- Accessibility gaps: poor contrast, missing labels, weak focus states, inaccessible dialogs, and dynamic state changes without clear affordance.
- Responsive breakage: clipped text, overflowing buttons, unstable fixed-format controls, or content overlap on mobile and desktop.
- Typography issues: viewport-scaled text, negative letter spacing, headings too large for their container, and weak hierarchy in dense panels.
- Interaction slop: hover/focus states resize layout, destructive actions lack clear confirmation, disabled states are unclear, or controls use unfamiliar shapes where standard icons fit.

## Process

1. Inspect the relevant components and CSS.
2. Run the app when needed and capture Playwright screenshots at desktop and mobile widths.
3. Report only concrete findings with `path:line`, impact, and the smallest useful fix.
4. If no issues remain, say so and name any verification gap.

Prefer fixing real issues over adding new visual systems.
