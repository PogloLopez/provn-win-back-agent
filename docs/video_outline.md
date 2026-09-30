# Video Outline

8 to 10 minutes, covering the five points the brief requires ([[win_back_agent_instructions]]). The facts are in [[architecture]], [[evaluation]] and [[ai_usage_log]]. This is only the running order.

| Min | Point | Show | Say (key lines) |
|---|---|---|---|
| 0:00-1:30 | **Approach** | Architecture diagram | Rules decide *who* may be contacted; AI decides *what* to offer within a pre-filtered menu; a second AI writes the email with placeholders; code checks both; a human approves everything. Why the split: judgement in the AI, money and consent in code. |
| 1:30-4:30 | **Demo** | Live site, Start demo | Offers streaming in; "Not contacted" with reasons (consent, too recent). Open C-1001: facts, offer cost, reason, highlighted values. Edit: type "10%" → blocked. Feedback "make it warmer" → spinner → routed to the copywriter → "Updated by the AI". Reject → trash. Approve → Copy email. |
| 4:30-6:30 | **Quality and failure plan** | [[evaluation]] table + telemetry numbers | Three systems compared; rules-in-prompt matched the pipeline on offers, and I say so. The code's measured value is the email: 34% of drafts blocked. Walk through one "looks right but wrong" case: "plus a a free parking pass". How a bad offer is stopped: rules → offer checks → copy checks → human; failures arrive flagged, never dropped. |
| 6:30-8:30 | **Mandatory AI question** | [[ai_usage_log]] entry 5 or 6 | Pick one and name it. *Entry 5:* the AI's diagram hid the rules engine and the business rules input; I drew my own and made it the reference, because it's what a product person reads first. *Or entry 6:* its reviewer called my baseline a strawman; the fairer baseline matched the pipeline on offers; I rewrote the claims instead of keeping the flattering version. |
| 8:30-9:45 | **With more time** | [[plan]] | Real send and redemption data to replace the invented conversion rates; learn from rejection reasons (which rule or prompt to change); scheduled runs instead of a button; a CRM or email integration; a larger, messier test set with resellers and repeat carts. |

Tips: speak to a product person (say "the club's rules", not "YAML"); keep the demo on the live URL; if Groq is slow, the "Not contacted" group still shows instantly.
