# Seawolves Cart Win-Back Agent

Every day, some Seattle Seawolves fans start buying tickets and leave before checking out. This project is a first, one-sprint version of an agent that follows up on those stale carts. It decides which fans are worth contacting, proposes a specific offer with a stated reason, and drafts an on-brand email. Nothing reaches a fan until a marketer approves it.

## How it works

1. **Rules engine (no AI).** Each cart is marked *skip*, *defer*, *caution* or *eligible*, with the reason. Fans without email consent are never contacted.
2. **Offer Strategist (AI).** Chooses an offer from the options the business allows for that fan's segment, weighing expected conversion against margin cost.
3. **Guardrails (rules).** Every offer is checked against the business rules. A failing offer is retried. If it keeps failing, it goes to the marketer flagged for attention instead of being dropped.
4. **Copywriter (AI).** Writes the email in the Seawolves voice, using placeholders instead of numbers so it can never state a wrong price or discount.
5. **Marketer review.** A simple screen to approve, edit, reject, or ask the AI to try again with feedback. Edits and feedback are classified and logged, so the rules and prompts can improve over time.

Every step is logged, so we can see where offers succeed, fail, or get corrected. A plain, unguarded AI run over the same carts serves as a baseline, which shows what the design adds.

## Documentation

- [Architecture](docs/architecture.md): the pipeline in detail
- [Decisions](docs/decisions.md): what was chosen and why
- [AI usage log](docs/ai_usage_log.md): how AI tools were used and redirected
- [Brief](docs/win_back_agent_instructions.md): the original assignment

## Status

Work in progress. Sections A (analysis), B (quality and failure plan) and C (AI usage) will be added here as the build completes.
