---
name: whatsapp-brain-maintainer
description: Maintain the durable cross-group AI learning brain from WhatsApp daily digests.
---

# WhatsApp brain maintainer

The daily group pages under `/workspace/extra/timeless-wiki/whatsapp/<group>/`
are episodic memory. The durable brain is the isolated `whatsapp/brain/`
subtree. Read only those WhatsApp daily pages and `coverage.md`; never read raw
WhatsApp JSONL, WhatsApp credentials, Timeless pages, or unrelated group memory.

Maintain these pages only:

- `brain/index.md` — navigation and scope, including links to every existing weekly synthesis.
- `brain/overview.md` — current cross-group synthesis and highest-value signals.
- `brain/tools-and-models.md` — tools, products, models, and practical status.
- `brain/patterns-and-techniques.md` — reusable workflows, prompts, architectures,
  and implementation patterns.
- `brain/lessons-and-gotchas.md` — repeated failure modes, security lessons, and
  evidence-backed cautions.
- `brain/open-questions.md` — unresolved claims and experiments worth pursuing.
- `brain/weekly/YYYY-MM-DD.md` — the dated weekly synthesis.

Deduplicate repeated discussion across groups and dates. Preserve the strongest
source-grounded version rather than copying every mention. Prefer knowledge that
is reusable outside the originating group: what was tried, what happened, why it
matters, and what remains uncertain. Separate reported claims, observed evidence,
and inference. Do not turn community chatter into work projects, owners,
deadlines, tasks, or personal facts. Do not promote anything into Timeless.

Every durable item must include source links to existing WhatsApp daily pages,
the originating group/date, and a confidence or evidence note. Never link to
Timeless pages or copy raw messages, phone numbers, credentials, or media.
Rewrite canonical pages rather than appending duplicate sections. Preserve human
edits where possible and keep the brain compact enough to read as a briefing.

The brain is read-only with respect to source pages and Drive. It may update only
the `whatsapp/brain/` subtree and its own operational log entry.

Resolve every relative link from the containing file's directory. Weekly pages are one directory deeper than overview pages; never copy overview links unchanged into `brain/weekly/`. Verify every output link and required frontmatter before reporting completion.

Exclude `coverage-status` pages from learning evidence; historical no-record checks do not establish facts about a group or the current archive.

Preserve every existing weekly snapshot when rebuilding the current week; never clear or replace the weekly directory. Keep historical snapshots linked from the brain index.

Before reporting completion, run `python3 /workspace/agent/knowledge-validator.py /workspace/extra/timeless-wiki --scope whatsapp` and fix every error. Top-level metadata keys such as `title` must start at column one. Links from `brain/weekly/` to group digests use `../../<group>/<date>.md`, not `../<group>/<date>.md`. If the validator is unavailable or fails, report the exact validation gap instead of claiming a successful rebuild.
