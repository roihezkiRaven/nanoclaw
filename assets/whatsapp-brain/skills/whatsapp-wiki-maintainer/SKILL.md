---
name: whatsapp-wiki-maintainer
description: Maintain concise WhatsApp group digests and durable knowledge from the allow-listed collector archive.
---

# WhatsApp wiki maintainer

The canonical shared wiki is `/workspace/extra/timeless-wiki/`. The only permitted source is the collector archive folder specified by the scheduled task. Do not use WhatsApp Web, credentials, or any messaging tool.

Use the Google Drive skill to list the archive folder. Consider only new `whatsapp-raw-*.jsonl` files whose Drive ID and modified time are absent or changed in `/workspace/extra/timeless-wiki/whatsapp-ingestion.json`. Process every eligible source individually, one at a time, without a numerical cap. After a source's durable update succeeds, checkpoint it immediately, so an interrupted run resumes safely.

For each source, first parse every JSONL record and partition the records by
`groupJid`. You must handle every distinct group represented in the source;
never summarize only the first or most active group. Resolve the group label
from the records and use a stable slug derived from that label. For each group,
extract only useful group-level information: decisions, commitments, deadlines,
blockers, project updates, and recurring themes. Do not copy raw messages. Write
or update one compact dated digest in `whatsapp/<group-slug>/YYYY-MM-DD.md` for
each represented group, even when the result is a short `No durable items` note.
Each digest must list all contributing source IDs in `sources` frontmatter and
the exact group label/JID in its provenance section. Update durable project,
task, decision, or topic pages only when the fact is supported and worth
retaining.

Every page must have frontmatter with `type`, `title`, `description`, `tags`, `generated`, and `sources`. Add a Markdown link or backlink only when its target page exists in the canonical wiki; create the supported target page first if needed. Preserve human-written material. Never include raw chat logs, phone numbers, credentials, or speculative claims.

After each pass, append a concise operational entry to `log.md`. If no archive source changed, make no wiki-content changes.
