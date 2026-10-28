---
name: whatsapp-wiki-maintainer
description: Maintain AI and technology learning digests from the allow-listed WhatsApp archive.
---

# WhatsApp wiki maintainer

The canonical WhatsApp wiki is the `whatsapp/` subtree of
`/workspace/extra/timeless-wiki/`. The only permitted source is the collector
archive folder specified by the scheduled task. Do not use WhatsApp Web,
credentials, or any messaging tool.

Use the Google Drive skill's `list` operation on the approved archive folder. Follow every `next_page_token` as `page_token` until `complete=true`; do not use a bounded tree or assume the first page is complete. Persist the inventory and reconcile all dates against the checkpoint, including older missed sources. An incomplete listing is a blocked inventory, never a successful no-change pass. Consider all new or changed `whatsapp-raw-*.jsonl` files whose Drive ID and modified time are absent or changed in `/workspace/extra/timeless-wiki/whatsapp-ingestion.json`. Process every eligible source individually, one at a time, without a numerical cap. After a source's durable update succeeds, checkpoint it immediately, so an interrupted run resumes safely.

Persist each complete source read immediately under `/workspace/agent/source-cache/<file-id>.json` with its observed metadata and complete text. Reuse it only when its ID and modified time still match the complete inventory. Never keep the only copy of fetched data in `/tmp` or process memory. Save partial progress before the runtime turn limit; resume cached sources without downloading them again. A fetched source is not an ingestion checkpoint until its digests are durable.

For each source, first parse every JSONL record and partition the records by
`groupJid`. You must handle every distinct group represented in the source;
never summarize only the first or most active group. Resolve the group label
from the records and use a stable slug derived from that label. If distinct
groupJIDs share a label, append a short stable JID suffix to each slug so they
cannot merge. For each group,
extract useful group-level information: tools and models, experiments, practical
techniques, implementation patterns, evidence, lessons, failure modes, useful
resources, emerging themes, and open questions. Treat these groups as an AI and
technology learning stream. A shared link, announcement, or opinion is not
durable knowledge without a concrete technical takeaway. Distinguish reported
claims, observed evidence, and inference, and preserve uncertainty. Do not turn
casual discussion into work projects, owners, commitments, deadlines, or tasks
unless the messages explicitly state them.
Do not copy raw messages. Write or update one substantive dated digest in
`whatsapp/<group-slug>/YYYY-MM-DD.md` for each represented group, even when the
result is a short `No durable items` note. Rewrite one canonical dated digest;
do not append duplicate "late developments" sections. When the source contains
enough material, preserve nuance with these sections: Summary, Tools and models,
Experiments and techniques, Lessons and gotchas, Resources, Emerging themes,
Open questions, and Explicit actions only when stated.
Each digest must list all contributing source IDs in `sources` frontmatter and
the exact group label/JID in its provenance section. Do not merge records from
different groups or infer a fact from another group.

This brain is strictly isolated from Timeless knowledge. It may create or update
only files below `whatsapp/` plus the WhatsApp ingestion checkpoint, a
WhatsApp-only `coverage.md`, and the operational `log.md`. Never create, edit,
backlink to, or delete anything under
`projects/`, `topics/`, `tasks/`, `people/`, `decisions/`, or the Timeless root
index. If a WhatsApp fact deserves durable treatment, retain it in the group's
digest rather than promoting it into the Timeless graph.

Every page must have frontmatter with `type`, `title`, `description`, `tags`, `generated`, and `sources`. Links and backlinks may target only existing pages below `whatsapp/`; never link into the Timeless graph. Preserve human-written material. Never include raw chat logs, phone numbers, credentials, or speculative claims.

After each pass, append a concise operational entry to `log.md`. If no archive source changed, make no wiki-content changes.

Link every daily digest from its group index and every group index from `whatsapp/index.md`. Refresh generated coverage counts when the archive grows; never leave September-only navigation hiding newer digests. Record each newly processed source's `disposition`, `outputs`, and a source-specific `reason` in its checkpoint so fetches cannot be mistaken for completed ingestion.

A no-record coverage check is `type: coverage-status`, not a daily digest or evidence of an empty current archive. A factual daily digest requires an exact source-backed group JID and nonempty sources; never use `cross-group` as its identity.


Partition by both exact group JID and original message UTC date, not ingestion or
upload date. Consolidate all contributing source revisions into that canonical
group/day digest. Reprocess the whole affected day when a late batch arrives;
do not replace its prior facts with only the latest batch. Record every source ID.
Detect malformed JSONL and record any lossless parser normalization explicitly;
never silently skip records and still claim complete ingestion. Captured daily-bot
summaries may be derivative/truncated and must not count as independent evidence.

A keyword list such as “tool mentioned; no benchmark” is not a substantive digest.
Read each complete group/day and explain its specific mechanism, result, caveat
or open question. A no-durable-items day can be one concise statement with
provenance; do not manufacture eight empty headings. Never copy raw messages,
participant identifiers or promotional invites. Checkpoint only after every
represented group/day is durably assessed. Rebuild the durable concept layer
when evidence changes; logs and daily digests remain supporting history.

The writable `/workspace/extra/timeless-wiki` mount is a scope-only draft. The host freezes, independently validates, publishes and promotes accepted content. A successful local edit is not accepted publication.
