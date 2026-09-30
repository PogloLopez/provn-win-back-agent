# Ship a Cart Win-Back Agent Before Marketing Has a CRM

Envorso Sports runs the fan-facing platform — ticketing, website, and mobile app — for the Seattle Seawolves of Major League Rugby. Ticketing, website, and mobile app are live with a real paying customer. CRM, marketing automation, and…

agentic-ai | multi-agent | full-stack | react | sports-tech | fan-engagement

**Estimated Time:** 40 minutess

**Difficulty:** Intermediate

**Status:** Not started

## What You'll Be Doing

Envorso Sports runs the fan-facing platform — ticketing, website, and mobile app — for the Seattle Seawolves of Major League Rugby. Ticketing, website, and mobile app are live with a real paying customer. CRM, marketing automation, and AI-driven personalization are on the near-term roadmap but not yet built.

Your product team wants a first agentic feature: a cart win-back agent. Every day, some fans start a ticket purchase and abandon it before checkout — a stale cart. Today, nobody follows up. The team wants an agent that looks at stale carts, decides which ones are worth a win-back offer, and proposes a specific offer a marketer can approve or reject — instead of a dashboard that just reports how many carts went stale.

You've been given a small sample dataset representing stale carts from the last 7 days. Build a first version of this feature.

| Cart ID | Fan ID | Seats | Section | Cart Value | Abandoned | Lifetime Tickets | Last Purchase | Email Opt-In |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| C-1001 | F-204 | 2 | Lower Bowl | \$96 | 3 hrs ago | 14 | 21 days ago | Yes |
| C-1002 | F-511 | 4 | Upper Deck | \$140 | 26 hrs ago | 0 | Never | Yes |
| C-1003 | F-092 | 1 | Lower Bowl | \$58 | 70 hrs ago | 3 | 180 days ago | No |
| C-1004 | F-333 | 6 | Club | \$540 | 1 hr ago | 40 | 9 days ago | Yes |
| C-1005 | F-777 | 2 | Upper Deck | \$70 | 96 hrs ago | 1 | 300 days ago | Yes |

## What to build

* **The agent(s):** Design and build (proof-of-concept level, not production-hardened) an agentic system — more than one prompt-and-response wrapper — that processes the stale cart data and, for each cart worth acting on, proposes a specific win-back offer (e.g., a discount, a section upgrade, a reminder-only nudge) with a stated reason. Not every cart needs to result in an offer — deciding which carts are worth acting on is part of the task.

* **The surface:** Build a UI (web, using React/Next.js patterns — a single component or small app is fine) where a marketer would actually see the agent's proposed offers and approve, edit, or reject each one before anything goes to a fan. A JSON dump is not sufficient — this must be something a non-technical marketer could use.

* **The README and video walkthrough** — see File Upload Requirements below.

## Constraints to Consider

* No CRM or marketing automation platform exists yet. You cannot assume Salesforce, HubSpot, or similar — your agent's output has to be usable by a marketer with nothing but this UI and, at most, a manual email/SMS send.

* You are the only engineer on this feature. There is no ML platform team to hand this off to — whatever monitoring or evaluation your agent needs, you have to design it yourself, not "the ops team will handle it."

* First step must be shippable in one sprint. Envorso Sports has one live customer today. Do not design a six-team, cross-league personalization engine — scope this to something a real marketer could use on Monday.

* A wrong offer costs real money and fan trust. The Seawolves are a real team with a real (and small) fan base — a bad or tone-deaf offer to a loyal fan is a bigger cost here than at a large e-commerce platform. Your design should reflect that this can't just "fail silently."

## AI Usage Guidance

We expect you to use AI tools. We evaluate how you use them — not whether you use them. Evidence of iteration, redirection, and critical evaluation scores higher than a polished output with no process documentation.

The single highest-signal indicator: your video answer to the mandatory AI question. If you cannot name a specific moment where you redirected AI output, evaluators will assume you did not.

Mandatory AI question for your video: Walk me through one moment where you disagreed with, pushed back on, or redirected what the AI gave you — and what you did instead. Name the specific moment. Explain what the AI produced that didn't meet the bar, what you did differently, and why.

Speak naturally. Communication is assessed on clarity of technical ideas and logical structure — not verbal polish, accent, or filler words. Because this role involves explaining agent behavior to non-ML people, also assess yourself on whether a product person (not just an engineer) could follow your explanation.

## What You'll Accomplish

* Design a multi-agent or multi-step agentic system with genuine separation of concerns, not a single prompt wrapper

* Ship a front-end surface that turns agent output into something a non-technical user can act on

* Define concrete, checkable criteria for whether an agentic feature is actually working

* Make a reasoned trade-off between agent capability, cost, and risk in a real, resource-constrained business context

* Explain agentic system behavior and failure modes clearly to a non-ML audience

## How Your Work Will Be Scored

* **Agentic System & Multi-Agent Architecture (30%):** A strong submission separates agent responsibilities into distinct steps with a real handoff, and can name a specific way its own design could fail along with a mitigation.

* **Full-Stack Delivery of Agent Output (18%):** A strong submission ships a UI a marketer could actually use to review and act on offers — not a JSON dump — and considers what happens when the agent is wrong.

* **Agent Quality, Evaluation & Engineering Leverage (20%):** A strong submission defines a concrete way to check if the agent's output is good, names a specific way it could look right but be wrong, and makes a reasoned cost/model trade-off.

* **Communication & Ambiguity Navigation (8%):** A strong submission explains the system and its failure modes clearly to a non-ML audience and names an independent scoping decision made along the way.

* **AI Fluency (14%):** A strong submission shows iteration, critical evaluation of AI output, and a specific, well-explained redirection moment in the video.

## What to Submit

### Agent + UI Code

Any File
Required
Format: no restrictions
Your working proof-of-concept — the agent logic that scores/decides on carts and proposes offers, plus the UI where a marketer reviews and acts on those proposals. Runnable or clearly readable is sufficient; production hardening is not expected.
Sign in to upload files

### README Document (Sections A, B, C)

Document · Section A: 300–500 words; Sections B and C as needed
Required
Format: .pdf, .doc, .docx, .rtf, .txt, .md
Three required sections.

* Section A — Written analysis (300–500 words): how you decided which carts deserve an offer, what offer logic you used and why, and what you would NOT do yet (scope you deliberately cut for the one-sprint constraint).

* Section B — Agent Quality & Failure Plan: describe, concretely, how you would know if this agent's offers were actually good (not just "it ran without errors"), and what could make it produce a bad offer without you noticing. Name at least one way you'd catch that before it reached a fan.

* Section C — AI Usage Log (Mandatory): This is not a trick. We want to see how you work with AI — not whether you used it. Document your AI collaboration process. For each significant interaction with an AI tool, briefly note: what you asked the AI to help with, what it gave you, and what you kept, changed, or rejected — and why. Three interactions documented is sufficient.
  Sign in to upload files

### Video Walkthrough

Video · 8–10 minutes
Required
Format: .mp4, .mov, .webm
Record as MP4 or MOV and upload directly on the Provn platform as a separate file.
Cover these five points:

* Approach — a summary of how you approached the problem and what you built

* Demo — a walkthrough of the agent and the UI, showing them working

* Quality & failure plan — walk through Section B of your README: how you'd know the offers are good, and how a bad one gets caught

* Mandatory AI question — one moment where you disagreed with, pushed back on, or redirected what the AI gave you. Name the specific moment, what the AI produced that didn't meet the bar, and what you did instead

* With more time — what you'd do differently or build next

Speak naturally. We assess clarity of technical ideas and whether a non-ML product person could follow you — not verbal polish, accent, or filler words.
