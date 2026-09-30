---
name: seawolves-voice-review
description: Review fan-facing copy (email drafts, fixtures, prompt examples, eval cases) against the Seattle Seawolves brand voice. Use when writing or reviewing Copywriter prompts, sample emails or copy-guardrail test cases.
---

# Seawolves Voice Review

The source of truth is `prompts/seattle_seawolves_persona.json`. Read it first. Never restate its values elsewhere.

For each piece of copy, check:

1. **Tone** matches `tone_attributes` and the `tone_by_contact_stage` entry for the cart's stage.
2. **Lexicon:** rugby terms are used naturally; no `banned_terms`; no American football language.
3. **Brand phrases:** only those listed in `fan_and_brand_phrases`, and none invented. Slogans appear only where they read naturally.
4. **Guardrails:**
   - every item in `communication_guardrails.rules`
   - no emojis
   - no scarcity or deadline claims without supporting data
   - no raw numbers, prices or percentages in drafts (values must be `{{placeholders}}`)
5. **Format** follows `output_style`: short, scannable, one call to action.

Report each issue with the quoted text, the rule it breaks, and a rewrite. Finish with `ON_VOICE` or `OFF_VOICE`.
