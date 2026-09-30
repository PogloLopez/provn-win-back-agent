# Seawolves Cart Win-Back Agent

Proof of concept for the Provn / Envorso Sports tech test. A deterministic Rules Engine (triage) finds the stale ticket carts worth acting on. LLM agents propose a guarded offer and an on-brand email for each one. A marketer approves, edits, rejects, or sends feedback in a minimal UI.

Read these before designing or changing behavior (all in `docs/`):
- [[win_back_agent_instructions]]: the brief and the scoring rubric
- [[architecture]]: pipeline, contracts, guardrails, telemetry, evaluation
- [[decisions]]: why things are the way they are. Add a row whenever you make or change a decision.
- [[ai_usage_log]]: add an entry whenever the user redirects or rejects AI output
- [[plan]]: build order and status. Update the status column in each PR

## Principles

- **Deterministic before LLM.** If code can decide it, code decides it. LLMs only choose inside sets that code has already constrained.
- **Single source of truth.** Rule values live in `config/` ([[architecture#Configuration]]). Never copy them into prompt text or components.
- **Never fail silently.** Every failure reaches the UI with a reason, and nothing is clamped or dropped without a trace.
- **Telemetry at every checkpoint.** Each pipeline stage writes an `events` row.
- **Dependencies over hand-written code**, but no frameworks the pipeline doesn't need (no LangChain, no rules-engine libraries).
- **Keep it simple.** This is a one-sprint POC. Build the thinnest end-to-end slice first.

## Stack and commands

- Stack: [[architecture#Stack]]. Secrets: `GROQ_API_KEY` in `.env` (see `.env.example`).
- `uv sync` installs dependencies. `uv run pytest` runs the tests. `uv run ruff check . && uv run ruff format --check .` lints. `uv run python -m winback.rules_engine` prints triage for the sample data. `uv run python -m winback.pipeline` runs the full pipeline live (Groq; telemetry to `DATABASE_URL`). `uv run pytest -m live` runs the live Groq tests.

## Workflow

The git flow and documentation rules are in `.claude/rules/`.

Agents:
- `reviewer`: run before every commit.
- `tester`: run before every PR.

Before merging any PR, stop, summarize the work to the user, and wait for their OK.
