# Documentation

- **Straightforward and non-verbose.** Tables and bullets over prose.
- **Every fact lives in one place.** Link to it rather than repeating it:
  - design goes in `architecture.md`
  - reasons go in `decisions.md`
  - AI collaboration goes in `ai_usage_log.md`
- **Links:** use Obsidian wikilinks (`[[architecture]]`, `[[decisions]] (D-005)`, `[[#Section]]`) in every Markdown file **except `README.md`**. In `README.md`, use standard relative Markdown links.
- **README.md:** slightly high-level language for a product and reviewer audience. It holds the submission sections A (analysis), B (quality and failure plan) and C (AI usage summary drawn from the log).
- **Keep docs current in the same commit as the change:** update `architecture.md` when behavior changes, add a row to `decisions.md` for each decision, and add an entry to `ai_usage_log.md` whenever the user redirects AI output.
