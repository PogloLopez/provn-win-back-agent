# Architecture

How the win-back pipeline works. The reasoning behind each choice is in [[decisions]]. The brief is in [[win_back_agent_instructions]].

## Pipeline

```mermaid
flowchart TD
    DATA[("STALE CARTS DATA")] ==> RE["RULES ENGINE (triage)<br/>deterministic"]
    TR("triage_rules.yaml") -.-> RE
    RE -- "SKIP / DEFER + reason" --> UI
    RE == "ELIGIBLE / CAUTION<br/>+ segment, reason codes" ==> OS["OFFER STRATEGIST<br/>LLM, large"]
    BR("business_rules.yaml") -.-> OS
    OS ==> OJ[/"Offer.json"/]
    OJ ==> OG{"Offer guardrails"}
    OG -. checks .-> BR
    OG -. checks .-> RE
    OG -- "fail: retry with violations, max 2" --> OS
    OG == pass ==> CW["COPYWRITER<br/>LLM, small"]
    P("persona.json") -.-> CW
    CW ==> DR[/"Email draft with placeholders"/]
    DR ==> CG{"Copy guardrails"}
    CG -. checks .-> OJ
    CG -. checks .-> P
    CG -- "fail: retry with violations, max 2" --> CW
    CG == pass ==> R["Render<br/>placeholders filled from Offer.json"]
    OG & CG -- "still failing" --> NA["NEEDS_ATTENTION<br/>+ safe default"]
    R ==> UI["MARKETER UI"]
    NA --> UI

    classDef data fill:#2e7d32,stroke:#1b5e20,stroke-width:3px,color:#fff,font-weight:bold
    classDef main fill:#1565c0,stroke:#0d47a1,stroke-width:3px,color:#fff,font-weight:bold
    classDef guard fill:#ef6c00,stroke:#e65100,stroke-width:2px,color:#fff
    classDef artifact fill:#eceff1,stroke:#78909c,stroke-width:1px,color:#37474f
    classDef config fill:#fafafa,stroke:#9e9e9e,stroke-width:1px,stroke-dasharray:4 3,color:#616161,font-size:12px
    classDef fail fill:#c62828,stroke:#8e0000,stroke-width:2px,color:#fff
    class DATA data
    class RE,OS,CW,UI main
    class OG,CG guard
    class OJ,DR,R artifact
    class TR,BR,P config
    class NA fail
```

Legend: **green** = data source, **blue** = main stages, **orange** = deterministic guardrails, **grey** = intermediate outputs, **dashed** = configuration, **red** = escalation to the marketer. Thick arrows show the main path.

After the UI (see [[#Marketer UI and feedback loop]]):

```mermaid
flowchart TD
    UI["MARKETER UI<br/>offer in detail box"] ==> A{"Marketer action"}
    A -- Approve --> S[/"Ready to send + Copy email"/]
    A -- Reject --> RC[/"Reason chip"/] --> T[/"Trash"/]
    A -- Edit --> ED["Edit overlay<br/>values bounded by business rules"]
    ED --> CG{"Copy guardrails"}
    CG -- pass --> UI
    CG -- "violations shown in overlay" --> ED
    ED -- "value edits: diffed in code" --> LOG2("Telemetry")
    ED -- "text edits" --> FA
    A == Feedback ==> FA["FEEDBACK ANALYST<br/>LLM, small"]
    FA == "offer issue" ==> OS["OFFER STRATEGIST"]
    FA == "wording issue" ==> CW["COPYWRITER"]
    OS & CW == "regenerated, re-checked by guardrails" ==> UI
    FA -- "rules / persona issue" --> LOG("Logged for human review")

    classDef main fill:#1565c0,stroke:#0d47a1,stroke-width:3px,color:#fff,font-weight:bold
    classDef guard fill:#ef6c00,stroke:#e65100,stroke-width:2px,color:#fff
    classDef artifact fill:#eceff1,stroke:#78909c,stroke-width:1px,color:#37474f
    classDef config fill:#fafafa,stroke:#9e9e9e,stroke-width:1px,stroke-dasharray:4 3,color:#616161,font-size:12px
    class UI,FA,OS,CW main
    class CG guard
    class S,RC,T,ED artifact
    class LOG,LOG2 config
```

A **run** processes every stale cart in the dataset at that moment, with per-cart LLM calls (no batching) at low concurrency (`src/winback/pipeline.py`). Each cart ends as `skipped`, `deferred`, `ready` (every guardrail passed), `needs_attention` (an escalation; safe defaults in place) or `failed` (an unexpected error, shown with its reason; the rest of the run continues), and outcomes stream out as each cart finishes. In the demo, a run starts from the "Start demo" button ([[decisions]] D-005).

Every step writes a telemetry event (see [[#Telemetry]]). Nothing is dropped silently: skipped, deferred and failed carts all appear in the UI with their reason.

## Rules Engine (triage)

Plain Python rules read from `config/triage_rules.yaml`. The output per cart is:

| Outcome | Meaning | LLM involved |
|---|---|---|
| `SKIP` | Never contact (hard rule, e.g. no email opt-in) | No |
| `DEFER` | Not yet (e.g. abandoned too recently); check again next run | No |
| `CAUTION` | Passes hard rules, but risk signals score above a threshold; the LLM is told to handle it carefully and the UI marks it | Yes |
| `ELIGIBLE` | Normal path | Yes |

The Rules Engine also assigns the **segment** (e.g. premium, loyal, first-timer, lapsed) and the **contact stage** (early / mid / late). The segment decides which offers the Strategist is allowed to choose. The contact stage decides the Copywriter's tone (`tone_by_contact_stage` in the persona).

Rule order: all `skip` rules, then `defer`, then caution scoring. Every result carries reason codes (`SKIP_*`, `DEFER_*`, `SIGNAL_*`, `SEGMENT_*`, `STAGE_*`). The Offer Strategist must cite these codes in `reason_codes_cited`.

Expected triage for the sample data, which is also the first golden set in [[#Evaluation]]:

| Cart | Outcome | Why |
|---|---|---|
| C-1001 | ELIGIBLE | Loyal fan (14 tickets), 3 h ago, early stage |
| C-1002 | ELIGIBLE | First-time buyer, 4 seats, 26 h ago; acquisition value |
| C-1003 | SKIP | No email opt-in |
| C-1004 | DEFER | 1 h ago, below the minimum contact delay; highest-value cart, so re-checked next run |
| C-1005 | CAUTION | 96 h ago, 1 lifetime ticket, last purchase 300 days ago |

## Configuration

Each value lives in exactly one file ([[decisions]] D-004).

| File | Owns | Read by |
|---|---|---|
| `config/triage_rules.yaml` | hard skips (consent, suspected reseller, dormant fan, outside window), minimum contact delay, contact-stage windows, segment definitions, caution scoring | Rules Engine |
| `config/business_rules.yaml` | per segment: allowed offer types, discount range (%), max offers, absolute $ cap on the total; tighter cap for CAUTION carts. Offer catalogue (`discount_pct`, `free_parking`, `extra_seat`, `seat_upgrade`, `early_entry`) with **margin loss** and **illustrative** conversion rate for each option and level; these numbers are invented and the README says so | Offer Strategist, offer guardrails, UI edit form |
| `config/models.yaml` | model, temperature and reasoning effort per role; number of guardrail retries | LLM client, pipeline |

## Offer Strategist

- **Input:** static prefix (system prompt) followed by one cart (cart facts, triage result, policy caps, and a menu of allowed options already filtered by segment, discount range and $ cap). Each option shows its cost, illustrative conversion rate and `expected_value_usd`, computed in code ([[decisions]] D-027). The prompt is `prompts/offer_strategist.md`.
- **Output:** strict JSON schema (Pydantic model), for example:

```json
{
  "cart_id": "C-1001",
  "decision": "offer",
  "offers": [{ "type": "free_parking", "value": true }],
  "reason": "Loyal fan, abandoned 3 h ago; a low-cost perk is enough, a discount would waste margin.",
  "reason_codes_cited": ["SEGMENT_LOYAL", "STAGE_EARLY"],
  "confidence": 0.7
}
```

`decision` can be `offer`, `reminder_only` or `no_offer`.

## Guardrails

All checks are deterministic, and each one returns a list of violations.

**Offer guardrails:**
- offer type allowed for the segment
- value within the allowed range
- total cost within the $ cap
- `reason` present, and `reason_codes_cited` is a non-empty subset of the cart's triage codes, so the reason is grounded in facts
- warning (not a block) when the most expensive menu option was chosen although a cheaper one was allowed
- a Groq outage or off-schema reply counts as a failed attempt (`LLM_UNAVAILABLE`, `BAD_JSON`), so it ends in NEEDS_ATTENTION, not a crash

**Copy guardrails:**
- placeholders ⊆ allowed set derived from the offer JSON
- required placeholders present
- no raw digits, `%` or `$` outside placeholders
- no `banned_terms` from the persona and no emojis
- no scarcity or deadline claims (`scarcity_terms` in the persona)
- where each placeholder meets its neighbours once rendered: no doubled word ("free free matchday parking") and no article or quantity word before a number ("a 10% off", "a couple of 2 seats"). A draft can pass every template rule and still read wrong once filled in ([[decisions]] D-031)
- no mention of an offer that was not granted (each offer's `keywords` in the business rules), which catches an email promising "free parking" in plain words

**Failure policy:**
1. Re-prompt with the violations, up to 2 retries.
2. If it still fails, the cart becomes `NEEDS_ATTENTION` in the UI, with the violations, the last attempt and a deterministic safe default (reminder only). Values are never clamped silently.

## Copywriter and rendering

- **Input:** offer JSON, section, contact-stage tone, the CAUTION flag, and each allowed placeholder with the exact text it renders to (so sentences read naturally around it). The persona is in the cached system prompt (`prompts/copywriter.md`).
- **Placeholders:** `{{section}}`, `{{seats}}` ("1 seat" or "2 seats"), `{{checkout_link}}` (required) and one per granted offer (required), named after the offer type and rendered from its `phrase` in the business rules.
- **Output:** strict JSON with `subject` and `body`. Every value is a placeholder, so the model cannot write a wrong number.
- **Rendering:** Jinja2 with `StrictUndefined` fills the placeholders after the copy guardrails pass.
- **On escalation:** a plain, always-valid template draft is used, so the marketer still has an email to edit ([[decisions]] D-028).

## Marketer UI and feedback loop

A minimal Next.js app built with shadcn/ui components; animations use `motion`.

1. **Landing:** a single "Start demo" button, which starts a real run.
2. **Workspace:**
   - A platform shell fades in. Its modules (e.g. Campaigns, Segments, Analytics) are visibly disabled, to show what v1 deliberately leaves out.
   - A side queue fills with offers one at a time as each cart finishes the pipeline, streamed from the API with server-sent events.
   - Queue items carry `CAUTION` and `NEEDS_ATTENTION` badges.
   - `SKIP` and `DEFER` carts sit in a collapsed "Not contacted" group, each with its reason.
3. **Detail box:** clicking a queue item opens a box in the center of the screen with the cart facts, the triage reason, the offer and its reason, and a preview of the rendered email. It has four buttons:

| Button | Effect |
|---|---|
| Approve | Status "Ready to send". The email is shown with a Copy button (there is no CRM) |
| Reject | One-click reason chips that map to `feedback_category` (Too generous → `offer_too_generous`, Wrong tone → `tone_off`, Shouldn't contact → `should_not_contact`, Other → `other`), then the item drops into a trash can |
| Edit | An overlay covers about 75% of the detail box. Values are form controls bounded by the business rules. The text is a plain-textarea template, with a live preview that shows values as highlighted chips. Saved text is re-checked by the copy guardrails |
| Feedback | A pop-up with a text box. On send, a spinner shows while the Feedback Analyst routes the feedback and the target agent regenerates. The new result (offer or email) replaces the old one, with the changes highlighted |

**Feedback Analyst output:** `feedback_category` (offer_too_generous, offer_too_weak, wrong_offer_type, tone_off, factual_error, off_brand, should_not_contact, other), `target_component` (triage, business_rules, offer_strategist, copywriter, persona), `severity` (low, medium, high), `summary`, and `instruction` (the concrete change for the target agent). Only `offer_strategist` and `copywriter` are routed automatically, and the instruction is passed to that agent as feedback; the other targets are logged for a human to act on. The prompt is `prompts/feedback_analyst.md`.

For edits to structured values, the diff is computed in code (e.g. 20% → 15% means `offer_too_generous`). Only text edits go to the Feedback Analyst.

## API

FastAPI (`src/winback/api.py`) over a review service (`src/winback/review.py`) that stores runs and one card per cart (`runs` and `cards` tables, next to `events`).

| Endpoint | Purpose |
|---|---|
| `POST /api/runs` | start a run (429 if the previous one started too recently; the public demo spends the Groq free tier) |
| `GET /api/runs/{id}/stream` | server-sent events: one `card` event per cart as it finishes, then `done` (telemetry failure count) or `run_failed` (reason; not `error`, which EventSource reserves). Each run streams once: 404 unknown, 409 already streamed, so a browser reconnect cannot re-run the LLMs; the UI closes the stream on `done` |
| `GET /api/runs/{id}/cards` | all cards of a run |
| `GET /api/cards/{id}/options` | allowed offer values, caps and placeholders for the edit form |
| `POST /api/cards/{id}/approve` | re-checks every guardrail, then marks it ready to send |
| `POST /api/cards/{id}/reject` | `{reason}`: one of `too_generous`, `wrong_tone`, `should_not_contact`, `other` |
| `POST /api/cards/{id}/edit` | `{offers?, subject?, body?}`; guardrail violations come back as 422 with the list |
| `POST /api/cards/{id}/feedback` | `{text}`: Feedback Analyst classifies and routes it; returns the regenerated card and a note |

## Models

All models run on Groq with strict JSON-schema outputs. Model IDs live in `config/models.yaml`.

| Role | Model | Why |
|---|---|---|
| Offer Strategist | `openai/gpt-oss-120b` | The judgement step; largest model |
| Copywriter | `openai/gpt-oss-20b` | Tightly constrained and fully checked by guardrails |
| Feedback Analyst | `openai/gpt-oss-20b` | Classifies into a fixed taxonomy |
| Baseline | `openai/gpt-oss-120b` | Same model as the Strategist, for a fair comparison |

The static prompt content always comes first so that provider-side prompt caching applies where available. The free tier has rate limits, so calls run with low concurrency and retry with backoff on HTTP 429.

## Telemetry

A single `events` table, written with SQLModel: Postgres on Supabase when deployed and SQLite locally, selected by `DATABASE_URL`. Columns: `run_id, cart_id, stage, status, reason_codes, payload, model, tokens_in, tokens_out, cached_tokens, latency_ms, attempt, created_at`.

Stages: `triage`, `offer`, `offer_guardrail`, `copy`, `copy_guardrail`, `render`, `ui_action`, `feedback`.

A failed telemetry write is logged and counted, the UI shows "telemetry degraded", and it never stops a fan's offer from being processed ([[decisions]] D-026). Supabase connection strings are accepted as copied (the driver and pooler options are normalized in code).

## Evaluation

- **Golden set (pytest):** the expected triage outcomes above, plus synthetic adversarial carts (e.g. opted-out high value, reseller pattern, first-timer with a huge cart). These cover the hard constraints: C-1003 is never contacted, no offer exceeds its caps, and no raw values appear in copy.
- **Looks right but is wrong:** a fluent reason that cites facts the cart doesn't have (e.g. "loyal fan" for first-timer C-1002). This is caught by the `reason_codes_cited` check; golden cases assert it.
- **Baseline run:** one plain LLM call over the same dataset (no Rules Engine, business rules or guardrails). Its offers are scored with the same guardrail checks, and the two runs are compared on violations, cost of the offers made, and carts wrongly contacted.
- **Online metrics:** guardrail pass rate, retry and `NEEDS_ATTENTION` rate, approve / edit / reject rate, edit magnitude, and rejections by `feedback_category`.

## Layout (planned)

```
config/                   triage_rules, business_rules, models
data/stale_carts.csv
prompts/                  persona + system prompts
src/winback/              triage, agents, guardrails, render, telemetry, api
tests/
web/                      Next.js marketer UI
```

## Stack

- **Python 3.13 with uv:** `groq`, `pydantic`, `pyyaml`, `jinja2`, `tenacity`, `fastapi`, `sqlmodel`, `psycopg`, `pytest`, `ruff`.
- **Web:** Next.js, shadcn/ui, `motion`.
- **Deploy:** Vercel (the UI, and FastAPI as a Python function) plus Supabase Postgres. The public demo spends the Groq free tier, so "Start demo" is rate-limited.
- **Not used:** rules-engine libraries or agent frameworks ([[decisions]] D-017).
