# Construction Plan

One PR per row, in order. Design is in [[architecture]].

| # | Branch | Delivers | Priority | Status |
|---|---|---|---|---|
| 0 | `feature/harness` | Design docs, persona, Claude Code harness | Must | Done |
| 1 | `feature/triage` | Dataset, `triage_rules.yaml`, Rules Engine, golden tests | Must | In PR |
| 2 | `feature/offer-agent` | `business_rules.yaml`, `models.yaml`, Groq client, Offer Strategist, offer guardrails with retry → NEEDS_ATTENTION, telemetry | Must | |
| 3 | `feature/copywriter` | Copywriter, copy guardrails, render, CLI end-to-end run (first full slice) | Must | |
| 4 | `feature/api` | FastAPI: streamed run, marketer actions, Feedback Analyst | Must | |
| 5 | `feature/ui` | Next.js: Start demo, queue, detail box, 4 actions (plain version) | Must | |
| 6 | `feature/eval` | Baseline run and comparison report | Must | |
| 7 | `feature/deploy` | Deploy ([[decisions]] D-022) | Should | |
| 8 | `feature/polish` | Trash animation, edit chips, disabled platform shell | Could | |
| 9 | `docs/submission` | README sections A–C, video outline | Must | |
