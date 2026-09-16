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
recordings, audio, video, and raw media. Each successful source is checkpointed
immediately so a failed run resumes without a hard source cap.

WhatsApp processing reads only the allow-listed collector archive, produces
compact dated group digests, and never copies raw messages into the graph.

Daily validation checks source fingerprints, malformed frontmatter, duplicate
pages, unresolved backlinks, and stale checkpoints. Drive mirrors export only
knowledge Markdown and preserve the existing folder layout.

Run the repository validator against a local wiki export with:

```bash
python3 scripts/validate-knowledge-wiki.py /path/to/timeless-wiki
```
