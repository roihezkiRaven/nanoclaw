---
name: timeless-brain-maintainer
description: Maintain a compact cross-page synthesis of the canonical Timeless knowledge graph.
---

# Timeless brain maintainer

The canonical Timeless pages under `/workspace/extra/timeless-wiki/` are the
semantic source of truth. The durable synthesis is the isolated `brain/`
subtree. Read only canonical Timeless Markdown pages and `index.md`; never read
the WhatsApp subtree, raw Drive exports, credentials, transcripts, media, or
unrelated group memory.

Maintain only these files:

- `brain/index.md` — navigation and scope, including links to every existing weekly synthesis.
- `brain/overview.md` — highest-value cross-domain synthesis.
- `brain/active-work.md` — active projects and tasks, with status grounded in
  canonical pages.
- `brain/themes.md` — recurring topics and relationships across pages.
- `brain/decisions-and-risks.md` — decisions, assumptions, and unresolved risks.
- `brain/stale-or-unresolved.md` — stale pages, missing next steps, and
  explicitly unresolved items.
- `brain/weekly/YYYY-MM-DD.md` — the current weekly synthesis.

Read all existing canonical pages before rebuilding; do not use a numerical
cap. Deduplicate repeated facts and preserve useful human edits where
possible. Each brain page must have frontmatter with `type`, `title`,
`description`, `tags`, `generated`, and `sources`. Every substantive claim
must link to one or more existing canonical Timeless pages. Mark inferences,
uncertainty, stale status, and conflicts explicitly. Never invent owners,
deadlines, status, relationships, or decisions.

For current state, prefer each project's dated current-status section over historical snapshots and old tasks. A source cited somewhere in the graph does not prove its current project facts were consolidated. Surface missing project overviews, contradictory status, uncertain client attribution and stale rollups as defects. Never carry an old unresolved choice forward after later evidence describes implementation; never infer a deployment succeeded from a plan or deadline. Link current project entry points so newly ingested clients and workstreams are discoverable.

Keep the brain compact and navigable. Do not copy raw notes, credentials,
transcripts, media, WhatsApp content, or whole source pages. Do not update
anything outside `brain/` except one concise operational log entry. Do not
change source pages or Drive content. If there is no evidence for a claim,
omit it or place it under unresolved questions with a source link.

Before finishing, run the knowledge-wiki validator, repair broken links, and
report source-page coverage and output paths.

Resolve every relative link from the containing file's directory. Weekly pages are one directory deeper than overview pages; never copy overview links unchanged into `brain/weekly/`.

Preserve every existing weekly snapshot when rebuilding the current week; never clear or replace the weekly directory. Keep historical snapshots linked from the brain index.
