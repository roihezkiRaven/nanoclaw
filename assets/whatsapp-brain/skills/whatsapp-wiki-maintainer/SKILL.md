---
name: whatsapp-wiki-maintainer
description: Maintain concise WhatsApp group digests and durable knowledge from the allow-listed collector archive.
---

# WhatsApp wiki maintainer

The canonical WhatsApp wiki is the `whatsapp/` subtree of
`/workspace/extra/timeless-wiki/`. The only permitted source is the collector
archive folder specified by the scheduled task. Do not use WhatsApp Web,
credentials, or any messaging tool.

Use the Google Drive skill's `tree` operation with `max_depth: 0` and a limit large enough for the complete folder to enumerate the archive folder; do not use a capped search or assume the first page is complete. Consider only new `whatsapp-raw-*.jsonl` files whose Drive ID and modified time are absent or changed in `/workspace/extra/timeless-wiki/whatsapp-ingestion.json`. Process every eligible source individually, one at a time, without a numerical cap. After a source's durable update succeeds, checkpoint it immediately, so an interrupted run resumes safely.

For each source, first parse every JSONL record and partition the records by
`groupJid`. You must handle every distinct group represented in the source;
never summarize only the first or most active group. Resolve the group label
from the records and use a stable slug derived from that label. For each group,
extract useful group-level information: context, decisions, commitments,
deadlines, blockers, project updates, technical details, and recurring themes.
Do not copy raw messages. Write or update one substantive dated digest in
`whatsapp/<group-slug>/YYYY-MM-DD.md` for each represented group, even when the
result is a short `No durable items` note. When the source contains enough
material, preserve nuance with these sections: Summary, Developments, Decisions,
Actions and deadlines, Blockers or open questions, and Technical/context notes.
Each digest must list all contributing source IDs in `sources` frontmatter and
the exact group label/JID in its provenance section. Do not merge records from
different groups or infer a fact from another group.

This brain is strictly isolated from Timeless knowledge. It may create or update
only files below `whatsapp/` plus the WhatsApp ingestion checkpoint and the
operational `log.md`. Never create, edit, backlink to, or delete anything under
`projects/`, `topics/`, `tasks/`, `people/`, `decisions/`, or the Timeless root
index. If a WhatsApp fact deserves durable treatment, retain it in the group's
digest rather than promoting it into the Timeless graph.

Every page must have frontmatter with `type`, `title`, `description`, `tags`, `generated`, and `sources`. Links and backlinks may target only existing pages below `whatsapp/`; never link into the Timeless graph. Preserve human-written material. Never include raw chat logs, phone numbers, credentials, or speculative claims.

After each pass, append a concise operational entry to `log.md`. If no archive source changed, make no wiki-content changes.
