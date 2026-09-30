# Seawolves Cart Win-Back Agent

Every day, some Seattle Seawolves fans start buying tickets and leave before checking out. This is a first, one-sprint version of an agent that follows up on those stale carts. It decides which fans are worth contacting, proposes a specific offer with a stated reason, and drafts an on-brand email. Nothing reaches a fan until a marketer approves it.

**Live demo:** https://provn-win-back-agent.vercel.app. Press *Start demo*: the real agents run on the five sample carts and the offers appear as each one finishes.

## How it works

1. **Rules engine (no AI).** Each cart is marked *skip*, *defer*, *caution* or *eligible*, with the reasons. Fans without email consent are never contacted and never reach an AI.
2. **Offer Strategist (AI).** Chooses from a menu that code has already limited to what the club allows for that fan, with the cost and expected value of each option.
3. **Offer guardrails (rules).** Every offer is re-checked against the business rules. A failing offer is retried with the problems explained. If it keeps failing, the marketer gets a safe reminder, clearly flagged, instead of a silent drop.
4. **Copywriter (AI).** Writes the email in the Seawolves voice. Every number, perk and link is a placeholder, so the AI can never type a wrong price.
5. **Copy guardrails (rules).** Check placeholders, brand voice, urgency claims, perks that weren't offered, and how the sentence reads once filled in.
6. **Marketer review.** Approve (then copy the email, since there is no CRM yet), edit within the rules, reject with a one-click reason, or send feedback that goes to the right agent and comes back through the same checks.

Every step writes a telemetry event (to Supabase in the live demo), so any decision can be traced back.

## Run it locally

```bash
uv sync
```

```bash
uv run uvicorn winback.api:app --port 8010 --reload
```

```bash
npm --prefix web install
```

```bash
npm --prefix web run dev
```

Then open http://localhost:3000. Set `GROQ_API_KEY` and, optionally, `DATABASE_URL` in `.env` (see `.env.example`); without a database URL it uses local SQLite. Tests: `uv run pytest` (the live model tests run with `-m live`).

## Section A: Written analysis

**Which carts deserve an offer.** I split the decision in two. First, a deterministic rules engine decides *whether* a fan may be contacted at all, because those are business and legal questions an AI should not be trusted with. No email consent means skip, always. A cart abandoned under two hours ago waits for the next run instead of being thrown away: that is how the highest-value cart in the sample (a $540 Club cart from a 40-ticket fan) is handled. Borderline fans, such as a one-time buyer who lapsed 300 days ago, pass with a *caution* flag that both the AI and the marketer see. On the five sample carts that gives three offers (one of them flagged *caution*), one skip and one "later".

**What offer logic I used and why.** The club's rules live in two plain configuration files: who may be contacted, and what can be offered to whom (allowed perks, discount range and a dollar cap for each fan segment). The AI never sees an option it isn't allowed to choose. It gets a short menu, already priced, with an *illustrative* conversion rate and expected value for each option (these numbers are invented for the demo). Its job is the judgement a formula can't make: recognition perks for loyal fans rather than training them to wait for discounts, an acquisition perk for a first-timer, a light touch for a cautious case. In practice it gave a free early entry to the loyal fan, an extra seat to the first-time group buyer, and a reminder or a small discount to the cautious lapsed fan. When I simulated the premium cart becoming eligible on a later run, it chose a seat upgrade over a discount.

**What I deliberately did not build.** There is no CRM, no automatic sending and no scheduling: the marketer copies an approved email, and a run starts from a button. There is no learning from outcomes yet, because conversion data doesn't exist. The feedback and edit telemetry is collected so that it can inform rule changes later, but nothing changes the rules automatically. There is no A/B testing, no SMS and no personalisation beyond the cart data, and there is no multi-team or multi-club design. The disabled modules in the demo's sidebar are there on purpose, to make that scope cut visible.

## Section B: Agent quality and failure plan

**How I know the offers are good, beyond "it ran".** `docs/evaluation.md` is generated from live runs that compare three systems on the same carts, all scored by the same checks:

| System (3 live runs each) | Contacted too early | Carts breaking offer rules | Incentive cost |
|---|---|---|---|
| Plain AI, no rules | 1.0 per run | 2.3 per run | $121 per run |
| AI with the rules pasted into its prompt | 0 | 0 | $50 per run |
| This pipeline | 0 | 0 | $54 per run |

The honest reading: the *rules* make offers safe, whether they are in the prompt or in code. On five carts, a well-prompted model followed them. Where the code visibly earns its place is the email. Across every live run recorded, the copy checks blocked **34% of drafts** (29 of 85) before they could reach a fan: prices typed as raw numbers, a required detail missing, sentences that read wrong once filled in. The offer checks blocked none, and they stay as cheap insurance. Whether offers actually *convert* can only be measured after real sends. The plan for that is approval, edit and rejection rates by reason, then redemption, all tracked from the same telemetry.

**What could make it produce a bad offer without anyone noticing.** The main risk is output that looks right but is wrong. Examples found while building it:
- **A fluent reason that cites facts the fan doesn't have** (for example "loyal fan" for a first-timer). The AI must cite the rule codes behind its reason, and a check rejects codes that don't belong to that cart.
- **An email that passes every template rule but reads badly once filled in** ("plus a a free parking pass", "a couple of 2 seats"). Live runs produced both. The copy checks now also read the text as it will be rendered.
- **A misread instruction in the feedback loop.** In one live run the analyst turned "give a perk instead of a discount" into "a modest discount". The regenerated offer still goes through the same guardrails, and the marketer sees the routing note before approving.
- **Invented numbers treated as truth.** The conversion rates are illustrative, so an offer can be internally consistent and still commercially wrong. This is stated in the rules file, the UI hides nothing, and a marketer approves every send.

**How a bad offer is caught before it reaches a fan.** It has to get past, in order: the rules engine, the offer checks, the copy checks, and a human who sees the fan's data, the cost of the offer, the AI's reason and the final email with every system-filled value highlighted. When a check keeps failing, the card arrives marked *needs attention* with the reasons, never silently dropped. Every decision and correction is in the telemetry, which is how the 34% figure above was measured.

**Cost and model trade-off.** I used Groq's free tier: a large open model (gpt-oss-120b) for the offer, where judgement matters, and a small one (gpt-oss-20b) for the email and the feedback classification, which are tightly constrained and fully checked. A full demo run of the five carts used 10,000 to 14,000 tokens in the recorded telemetry, including retries. The main operational limit is the free tier's tokens-per-minute cap, which the client handles with backoff and the public demo with run and feedback caps.

## Section C: AI usage summary

I built this with Claude Code (Opus 5.5) as a pair: I set the design and made the calls, and it wrote code with a reviewer agent before every commit and a tester agent before every PR. The full log is in [docs/ai_usage_log.md](docs/ai_usage_log.md). Highlights:

1. **The persona and dataset from another AI were wrong.** The seat counts were glued onto the fan IDs, which I fixed by hand. The brand persona included made-up club lore; "Up The Orcas" turned out to be a Seattle cricket team. I had it checked against public sources and cut to verified phrases only.
2. **I redirected the design review.** The AI proposed a three-way triage; I added a fourth outcome, *caution*. It recommended Anthropic models; I switched to Groq's free tier with the same large/small split. I added the baseline comparison and the margin-versus-conversion idea myself.
3. **I rejected its diagram.** Its first pipeline diagram hid the rules engine and left out the business rules as an input to the AI. I drew my own and made it the reference.
4. **Its own reviewer changed my evaluation.** The reviewer agent called my first baseline a strawman and suggested a second one with the rules in the prompt. That baseline performed as well as the pipeline on offers, and I rewrote the claims to say so rather than keep the flattering version.

## Documentation

- [Architecture](docs/architecture.md): the pipeline in detail
- [Decisions](docs/decisions.md): what was chosen and why
- [Evaluation](docs/evaluation.md): the latest baseline comparison and guardrail numbers
- [AI usage log](docs/ai_usage_log.md): how AI tools were used and redirected
- [Build plan](docs/plan.md): the order it was built in
- [Brief](docs/win_back_agent_instructions.md): the original assignment
