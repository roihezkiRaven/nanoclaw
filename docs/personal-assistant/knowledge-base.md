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

Daily validation checks source fingerprints, malformed frontmatter, duplicate
pages, unresolved backlinks, and stale checkpoints. Drive mirrors export only
knowledge Markdown and preserve the existing folder layout.

Run the repository validator against a local wiki export with:

```bash
python3 scripts/validate-knowledge-wiki.py /path/to/timeless-wiki
```
