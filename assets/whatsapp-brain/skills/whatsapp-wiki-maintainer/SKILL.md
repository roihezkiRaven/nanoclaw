---
name: whatsapp-wiki-maintainer
description: Maintain concise WhatsApp group digests and durable knowledge from the allow-listed collector archive.
---

# WhatsApp wiki maintainer

The canonical shared wiki is `/workspace/extra/timeless-wiki/`. The only permitted source is the collector archive folder specified by the scheduled task. Do not use WhatsApp Web, credentials, or any messaging tool.

Use the Google Drive skill to list the archive folder. Consider only new `whatsapp-raw-*.jsonl` files whose Drive ID and modified time are absent or changed in `/workspace/extra/timeless-wiki/whatsapp-ingestion.json`. Process every eligible source individually, one at a time, without a numerical cap. After a source's durable update succeeds, checkpoint it immediately, so an interrupted run resumes safely.

For each source, extract only useful group-level information: decisions, commitments, deadlines, blockers, project updates, and recurring themes. Do not copy raw messages. Write or update a compact dated digest in `whatsapp/<group-slug>/YYYY-MM-DD.md`; use the source file ID, modified time, and group label in frontmatter. Update durable project, task, decision, or topic pages only when the fact is supported and worth retaining.

Every page must have frontmatter with `type`, `title`, `description`, `tags`, `generated`, and `sources`. Use Markdown links in `index.md` and reciprocal `## Backlinks` for related concepts. Preserve human-written material. Never include raw chat logs, phone numbers, credentials, or speculative claims.

After each pass, append a concise operational entry to `log.md`. If no archive source changed, make no wiki-content changes.
