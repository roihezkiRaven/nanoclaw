# Personal assistant operations

This document describes the deployed personal-assistant data flows. It intentionally excludes credentials, tokens, folder IDs, and WhatsApp group IDs; those stay in protected host configuration.

## Models and roles

| Role | Model | Reasoning | Authority |
| --- | --- | --- | --- |
| Personal Assistant | GPT-5.6 Terra | low | Conversational interface; reads the shared knowledge wiki only. |
| Timeless Brain | GPT-5.6 Luna | medium | Reads eligible Timeless notes and updates the shared wiki. |
| WhatsApp Brain | GPT-5.6 Luna | medium | Reads only the collector archive and updates the isolated WhatsApp wiki subtree. |

The two maintenance agents are not exposed on Slack or Telegram. The Personal Assistant has a read-only mount of the wiki; each maintenance agent has the one explicitly allow-listed read/write mount.

## Data kept and where

- `data/timeless-wiki/`: canonical local Markdown knowledge graph. It contains `index.md`, source-grounded concept pages, the operational `log.md`, and per-source ingestion checkpoints.
- `Timeless Knowledge` Drive folder: a mirrored, human-browsable copy of the Timeless portion of the local graph. The sync state file remains local and is never mirrored.
- `WhatsApp Knowledge` Drive folder: a separate mirrored, human-browsable copy of WhatsApp group digests only. It never contains Timeless projects/topics/tasks or raw archives.
- `WhatsApp Archive` Drive folder: raw text-only JSONL batches created by the collector. It is source material, not a user-facing knowledge base.
- `store/whatsapp-collector/`: local delivery queue, deduplication state, and heartbeat. It holds no long-term wiki content.
- `store/whatsapp-collector-auth/` and `config/google/`: protected authentication material. They are ignored by Git and must never be copied into prompts, docs, logs, or commits.

## Processing

### Timeless

At 02:30 UTC each day, Timeless Brain inventories the approved Timeless root and handles every changed eligible note individually. Eligible inputs are plaintext, Google Docs, and Google Sheets used as notes. It excludes transcripts, recordings, audio/video, raw-media sources, WhatsApp Archive files, and WhatsApp-derived digests. It never links to or promotes WhatsApp material into the Timeless graph. After each successful source update it checkpoints that Drive file ID and modified time, so interrupted work resumes without reprocessing completed notes.

Pages are compact and linked by topic, project, decision, task, or person. Each factual page records Drive provenance and marks inferences. The Brain never changes source Drive files or sends messages.

### WhatsApp

The collector is a user-level systemd service. It connects through the linked WhatsApp account, accepts only configured group JIDs, ignores outgoing messages and all non-text content, queues records durably, and uploads batches to `WhatsApp Archive`. Failed uploads stay queued for retry. It does not backfill old chat history.

At 03:30 UTC each day, WhatsApp Brain lists only that archive and processes each new JSONL batch individually. It partitions every batch by group JID and writes substantive dated learning digests only below `whatsapp/`. WhatsApp is treated as an AI/technology learning stream: digests emphasize tools and models, experiments, techniques, lessons, failure modes, resources, emerging practices, and open questions. It does not convert conversational chatter into work projects, people, owners, deadlines, or tasks. Distinct JIDs with the same display label receive separate stable folders. Timeless remains the work-oriented graph for projects, people, decisions, commitments, and tasks. WhatsApp Brain does not update Timeless projects, topics, tasks, people, or decisions, and does not retain raw chat text, phone numbers, or credentials in the graph. It cannot send WhatsApp messages.

### Drive mirror

At 04:15 UTC, `knowledge-wiki-sync.timer` mirrors local Timeless wiki pages to `Timeless Knowledge`; at 04:20 UTC, `whatsapp-wiki-sync.timer` mirrors only the local `whatsapp/` subtree to `WhatsApp Knowledge`. Both use the restricted writer credential and update only Drive files they created. They are intentionally after both maintenance jobs.

## Operating safely

- Add a WhatsApp group only after running the collector's group-list command and matching the exact displayed name and JID. Duplicate names require an explicit choice; never add every possible match by default.
- Keep the collector allowlist in protected host configuration, not Git.
- Use the bounded Drive inventory and the ingestion checkpoints; do not reintroduce raw transcript/media ingestion to save tokens.
- Verify services without exposing secrets: `systemctl --user status whatsapp-collector.service`, `systemctl --user status knowledge-wiki-sync.timer`, and `ncl tasks get <series-id> --group <group-id>`.
