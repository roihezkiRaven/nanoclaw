# Personal knowledge base

The existing OKF/Drive structure is canonical. This project enriches it; it
does not migrate or rename existing pages and folders.

## Existing graph

Keep `projects/`, `topics/`, `tasks/`, `people/`, `decisions/`, `whatsapp/`,
`Timeless Knowledge`, and `WhatsApp Knowledge` in place. Existing page IDs,
human-authored text, backlinks, and Drive locations are preserved.

## Additive conventions

Use the knowledge-base-demo ideas as process improvements:

- `inbox/` for unprocessed captures;
- `raw/` for immutable approved source notes (never transcripts or media);
- `meetings/` and `daily/` for derived summaries;
- `areas/` for ongoing responsibilities and the task single-source-of-truth;
- `templates/` for repeatable page shapes; and
- `archive/` for completed material without deleting history.

Every derived page carries `type`, `title`, `description`, `tags`, `generated`,
and `sources` frontmatter. Sources include the original Drive ID/URL and
observed modified time. Facts and inferences are labeled separately.

## Processing

Timeless processing reads every changed eligible note individually, including
meeting notes in Google Docs, Sheets, or plaintext. It excludes transcripts,
recordings, audio, video, raw media, the WhatsApp Archive, and WhatsApp-derived
digests. It never reads, links to, or promotes WhatsApp material into the
Timeless graph. Each successful source is checkpointed immediately so a failed
run resumes without a hard source cap.

WhatsApp processing reads only the allow-listed collector archive, partitions
every batch by group JID, and produces substantive dated learning digests only
under `whatsapp/`. The WhatsApp schema captures tools/models, experiments,
techniques, lessons, failure modes, resources, emerging themes, and open
questions. It does not infer work projects, people, owners, commitments,
deadlines, or tasks from group chatter. Duplicate labels receive a JID suffix
so distinct groups cannot merge. It never copies raw messages or promotes
pages into the Timeless `projects/`, `topics/`, `tasks/`, `people/`, or
`decisions/` directories.

The WhatsApp brain is a second, slower layer under `whatsapp/brain/`. It reads
only the daily WhatsApp pages, deduplicates repeated signals across groups, and
maintains durable cross-group pages for tools/models, reusable patterns,
lessons/gotchas, open questions, and weekly synthesis. It never reads raw
messages or writes outside the WhatsApp subtree.

Timeless now has the analogous `brain/` synthesis layer. It reads only the
canonical Timeless graph and maintains overview, active-work, themes,
decisions-and-risks, stale-or-unresolved, and weekly pages with links back to
the authoritative project/topic/task/person/decision pages. It never reads or
promotes WhatsApp material and never replaces the canonical graph.

The Personal Assistant's conversational memory is a separate small OKF bundle
under its agent group. The session hook loads only `memory/index.md` and the
memory definition; linked concepts are read on demand. Completed conversations
are archived separately, and the nightly reflection reviews them without
copying transcript noise into memory. Changing facts carry `as_of` and optional
`review_after` metadata, with freshness and contradiction findings recorded in
`memory/review.md`.

Daily validation checks source fingerprints, malformed frontmatter, duplicate
pages, unresolved backlinks, and stale checkpoints. Drive mirrors export only
knowledge Markdown and preserve the existing folder layout.

Run the repository validator against a local wiki export with:

```bash
python3 scripts/validate-knowledge-wiki.py /path/to/timeless-wiki
```

## Consolidation and publication contract

Source freshness, semantic review and publication freshness are separate signals.
A successful mirror does not prove that new source facts reached the brain. The
host independently inventories every approved source folder with pagination and
caches complete observed revisions outside the writers' mounts. A check date is
never substituted for an evidence date; no newly visible note means no invented
meeting update. Coverage pages expose pending revisions and distinguish captured
WhatsApp records from unknown upstream capture gaps.

Writers receive separate writable drafts under `data/knowledge-drafts/timeless`
and `data/knowledge-drafts/whatsapp`. The assistant reads the accepted
`data/timeless-wiki` mount read-only. Publication freezes the scoped draft,
regenerates navigation, validates it against protected evidence and retained
accepted knowledge, then uploads it and promotes that frozen snapshot. Failed
or concurrent draft edits cannot enter the accepted graph. Previously published
pages remain addressable; consolidation retains a redirect instead of silently
removing a page. The existing last-good synthesis fallback remains visible as
`degraded`; invalid source pages fail closed.

Each reviewed Timeless source records `consolidation_version: 2` and explicit
`project_assessments`. An update includes an exact primary-source excerpt and
the actual canonical fact with its nearby citation, not merely the source ID in
metadata. A no-change assessment identifies the existing retained fact or a
concrete out-of-scope reference. Ambiguous attribution identifies the competing
identities; an explicit project section cannot be blanket-dismissed. Accepted
updated assessments cannot later be replaced by generic no-change claims.
These checks establish traceability, not an automatic proof of semantic truth;
review representative current facts, contradictions and cross-project links
against original notes before accepting a repair.

A project has one current-status section dated by its supporting evidence,
with older observations kept as dated history. Client aliases resolve to one
canonical page; a redirect preserves old URLs. Cross-project syncs contribute to
each affected project and reusable concepts without equating similar names or
collapsing distinct workstreams. Concept pages explain what the idea is, when to
use it, how it works, evidence and limits, and related concepts. Meeting and
source archives stay behind evidence links rather than filling navigation.

WhatsApp audit maps every processed archive record to its exact group and UTC
message date, checks every contributing source, and detects duplicate or
missing digests. Late arrivals rebuild the entire day. Legacy literal newlines
are decoded losslessly and counted, never silently skipped. Community reports,
repeated bot summaries and independently tested results remain distinct.

The AI Engineering wiki has stable concept pages and separate public research,
private community evidence and original-report archives. Research tasks update
`work/knowledge/ai-engineering/wiki`; `engineering-wiki-sync.timer` publishes it
after the research passes. Old report links remain available in the archive;
creating another dated export is not the maintenance strategy.

Drive exports omit machine frontmatter, retain readable evidence information,
and translate local links to stable Drive file identities. Identity registration
precedes uploads so new pages can link to one another. Upload fingerprints use
the rendered export, making repeat publication idempotent. The watchdog also
checks engineering publication, degraded fallback, and eligible source revisions
pending longer than 26 hours; publication success does not hide ingestion lag.
