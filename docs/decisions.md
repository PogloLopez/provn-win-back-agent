# Decisions

One line per decision: what was chosen, why, and what was rejected. The design itself is in [[architecture]]. How AI shaped these decisions is in [[ai_usage_log]].

| ID | Decision | Why | Rejected |
| --- | --- | --- | --- |
| D-001 | The Rules Engine (triage) returns SKIP / DEFER / CAUTION / ELIGIBLE | A binary filter would drop C-1004, the highest-value cart, just for being too recent. CAUTION lets borderline carts through with a visible flag | Pass/fail filter |
| D-002 | Consent (email opt-in) is a hard SKIP, applied before any LLM call | Legal and trust risk. The LLM never sees these carts | Letting the LLM decide |
| D-003 | Segment and allowed offers are computed in code; the LLM chooses inside that set | Smaller prompt; the guardrails and the prompt share one rule set | LLM enforcing the rules itself |
| D-004 | Two rule files (plus `models.yaml` for model IDs), each value in exactly one: `triage_rules.yaml` (who is contacted) and `business_rules.yaml` (what can be offered). Prompts, guardrails and the UI read them | Separate copies would drift apart; the split matches the two inputs of the Offer Strategist | Rules duplicated in the prompt text |
| D-005 | Per-cart LLM calls with a cached static prefix. The demo triggers a run from "Start demo"; production would use a schedule | Caching gives the cost savings; batching causes shared failures and anchoring between carts | Several carts in one prompt |
| D-006 | Show conversion rate **and** margin loss for each offer level; conversion data is invented and disclosed | Stops the model from always choosing the biggest discount | Conversion rate only |
| D-007 | Offer and copy are separate agents with separate JSON contracts | Each step can be checked and measured on its own | One agent doing both |
| D-008 | Copy uses placeholders; values are filled in by Jinja2 (StrictUndefined) | The LLM cannot write a wrong number | LLM writing the values |
| D-009 | When a guardrail fails: retry with the violations (max 2), then NEEDS_ATTENTION in the UI with a safe default | Nothing fails silently and nothing is clamped silently; the marketer keeps continuity | Silent clamping; dropping the cart |
| D-010 | Persona is voice only, and runtime data rather than a skill | Offer logic belongs in business rules. A Claude Code skill serves the dev agent, not the runtime | Persona as a runtime skill |
| D-011 | Persona brand phrases limited to publicly verified ones | "Up The Orcas" (the Orcas are a Seattle cricket team), "The Pod" and others could not be verified | Keeping LLM-generated lore |
| D-012 | Feedback Analyst classifies marketer feedback and routes it to the Strategist or the Copywriter | Makes the loop useful as well as measurable | Feedback only logged |
| D-013 | Value edits are diffed in code; only text edits go to the LLM | Cheaper and deterministic | LLM for every edit |
| D-014 | Groq, with a large model for judgement and a small one for constrained steps (IDs in [[architecture#Models]]) | Generous free tier; both support strict JSON schema | Anthropic models (cost) |
| D-015 | Baseline run: a plain LLM call scored by the same checks | Shows what the guardrails and rules actually add | No comparison |
| D-016 | Telemetry in one `events` table: Supabase Postgres when deployed, SQLite locally | Queryable, persists on serverless, same code in both places | JSONL; external tracing tools |
| D-017 | No rules-engine library and no agent framework | About 6 rules and a straight-line pipeline; wiring a framework is more code | durable_rules, LangChain / LangGraph |
| D-018 | Git flow: feature → develop through PRs, atomic commits while working, squashed into 3–4 logical commits before the PR, then rebase-and-merge; reviewer before each commit, tester before each PR | The reviewer sees small diffs, and develop gets a short linear history | GitHub squash-merge (1 commit per PR); merge commits |
| D-019 | The offer `reason` must cite triage reason codes; edited text is re-checked by the copy guardrails | Catches fluent but ungrounded reasons, and marketer typos with raw prices or banned terms | Checking only that a reason exists |
| D-020 | Demo UI: "Start demo" → disabled platform shell → streamed offer queue → detail box with Approve / Reject / Edit / Feedback | Real inference feels live; the disabled modules show the scope cut; each action is one click | Dashboard table; JSON view |
| D-021 | The email preview is shown before approval; rejection takes a one-click reason | The marketer never approves unseen wording; rejections become explainable telemetry | Email only after approval; reject with no reason |
| D-022 | Deploy on Vercel plus Supabase | One platform for the UI and API; Postgres persists telemetry | Render (cold starts), SQLite on serverless (temporary storage) |
| D-023 | Copy guardrails check against Offer.json and the persona, not the rules | The draft holds placeholders, not values; the values were already checked at the offer step | Re-checking the draft against business rules and the Rules Engine |
| D-024 | `SKIP_SUSPECTED_RESELLER` and `SKIP_DORMANT` use proxies (seat count; lifetime tickets plus time since purchase) | The dataset has no resale or attendance history | Leaving them out; inventing columns |
