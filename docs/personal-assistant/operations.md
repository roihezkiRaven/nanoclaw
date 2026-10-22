# Personal assistant operations

This document describes the deployed personal-assistant data flows. It intentionally excludes credentials, tokens, folder IDs, and WhatsApp group IDs; those stay in protected host configuration.

## Source preservation and health monitoring

Commit and push authorized code, tests, templates and deploy configuration before
considering an implementation complete. Private knowledge, credentials, provider
state, logs, working notes and recovery archives stay outside Git. Check both
the workstation and server for uncommitted source changes, and scan the staged
files for secrets before pushing to this public repository.

The watchdog reads installation identities from protected
`config/report-watchdog.json`; `config-examples/report-watchdog.json` shows the
shape with synthetic values. Replace every example identifier before enabling
the monitor. Actual owner destinations and task IDs must never go in Git.
Failed knowledge syncs, or no successful run for 36 hours, receive one bounded
retry and a direct owner alert independent of model availability. Running syncs
are left alone. Report delivery still requires actual platform receipts.

Knowledge publishing retains daily timers and adds Sunday publication after the
weekly rebuilds. Source reads and upload IDs persist after each successful step;
corrupt sync state fails closed. Private runtime state requires protected backup;
Git is a backup of code and configuration templates, not owner data.

For a browser handoff, set `NANOCLAW_SSH_HOST` (or ignored `config/browser-handoff.json`, using the example in `config-examples/`) to the configured SSH destination;
the public helper contains no installation address.

## Models and roles

Codex is pinned to 0.160.0 in `container/cli-tools.json`. GPT-6 requests require
the newer client; updating the displayed catalog alone is insufficient. Telegram
`/models` reads the account catalog refreshed by Codex at provider startup.

OneCLI 1.41.0 supplies a placeholder workspace ID that newer Codex rejects during
workspace discovery (upstream issue `onecli/onecli#577`). The host replaces only
workspace and plan metadata using protected
`data/onecli/<agent-group-id>-codex-identity.json` files. Access and refresh tokens
remain `onecli-managed`; OneCLI continues injecting and refreshing credentials.
Update this metadata if the connected ChatGPT account or workspace changes.
The repair skips native stubs with real workspace IDs, so a gateway release
containing the upstream fix can replace this workaround.

| Role | Model | Reasoning | Authority |
| --- | --- | --- | --- |
| Personal Assistant | GPT-6 Sol | low | Conversational interface; reads the shared knowledge wiki only. |
| Timeless Brain | GPT-6 Luna | medium | Reads eligible Timeless notes and updates the shared wiki. |
| WhatsApp Brain | GPT-6 Luna | medium | Reads only the collector archive and updates the isolated WhatsApp wiki subtree. |

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

At 05:30 UTC on Sundays, the Timeless brain maintainer reads all canonical
Timeless Markdown pages (excluding `whatsapp/`) and rebuilds the isolated
`brain/` synthesis. It deduplicates cross-page themes, active work, decisions,
risks, stale items, and unresolved questions, preserving links to authoritative
pages. It does not read raw Drive notes or write outside the `brain/` subtree.

### WhatsApp

The collector is a user-level systemd service. It connects through the linked WhatsApp account, accepts only configured group JIDs, ignores outgoing messages and all non-text content, queues records durably, and uploads batches to `WhatsApp Archive`. Failed uploads stay queued for retry. It does not backfill old chat history.

At 03:30 UTC each day, WhatsApp Brain lists only that archive and processes each new JSONL batch individually. It partitions every batch by group JID and writes substantive dated learning digests only below `whatsapp/`. WhatsApp is treated as an AI/technology learning stream: digests emphasize tools and models, experiments, techniques, lessons, failure modes, resources, emerging practices, and open questions. It does not convert conversational chatter into work projects, people, owners, deadlines, or tasks. Distinct JIDs with the same display label receive separate stable folders. Timeless remains the work-oriented graph for projects, people, decisions, commitments, and tasks. WhatsApp Brain does not update Timeless projects, topics, tasks, people, or decisions, and does not retain raw chat text, phone numbers, or credentials in the graph. It cannot send WhatsApp messages.

At 05:00 UTC on Sundays, the WhatsApp brain maintainer reads only the daily
WhatsApp pages and rebuilds the cross-group `whatsapp/brain/` layer. It
deduplicates recurring signals and records reusable tools, patterns, lessons,
and open questions with links back to existing WhatsApp pages. This layer is
not a second Timeless graph and never reads raw chat or writes outside the
WhatsApp subtree.

### Drive mirror

At 04:15 UTC, `knowledge-wiki-sync.timer` mirrors local Timeless wiki pages (including `brain/`) to `Timeless Knowledge`; at 04:20 UTC, `whatsapp-wiki-sync.timer` mirrors only the local `whatsapp/` subtree to `WhatsApp Knowledge`. Both use the restricted writer credential and update only Drive files they created. They are intentionally after the maintenance jobs.

## Operating safely

### Google authorization

The reader, writer, and Calendar credentials use offline OAuth grants. Their
OAuth projects must use Google Auth Platform → Audience → **In production**;
external apps in Testing issue refresh tokens that expire after seven days.
Calendar uses the reader OAuth client; check the writer client's actual project
separately. Personal-use apps can remain unverified where Google's policy permits.

Keep the writer's existing OAuth client when renewing consent: `drive.file`
access to existing mirror files belongs to that app. Changing clients can leave
the writer able to create new files but unable to update its existing mirrors.
Validate access to a file recorded in `.drive-sync.json`, not just token refresh.

After changing publishing status, obtain fresh grants for all three modes. From
an interactive terminal, connect with `ssh -L 8080:127.0.0.1:8080 assistant@your-server.example`,
then run `.venv-gdrive/bin/python tools/gdrive_assistant.py reader auth` from
`/home/assistant/nanoclaw`, repeating for `writer auth` and `calendar auth`.
Open each authorization URL locally and complete consent. Explicit `auth`
replaces the old grant even if its access token is still valid.

Verify each mode with `reader check`, `writer check`, and `calendar check`, then
retry the two wiki sync services. Routine access-token renewal is automatic.
Revoked or expired refresh grants require consent; restarting the broker cannot
repair them. Production grants can still be revoked by the account or its policies.

- Add a WhatsApp group only after running the collector's group-list command and matching the exact displayed name and JID. Duplicate names require an explicit choice; never add every possible match by default.
- Keep the collector allowlist in protected host configuration, not Git.
- Use fully paginated Drive inventory and the ingestion checkpoints; do not reintroduce raw transcript/media ingestion to save tokens.
- Verify services without exposing secrets: `systemctl --user status whatsapp-collector.service`, `systemctl --user status knowledge-wiki-sync.timer`, and `ncl tasks get <series-id> --group <group-id>`.

### WhatsApp collector recovery

Missing, corrupt, or logged-out credentials exit with status 78; systemd does not
restart until the operator relinks. Credential and Signal-key replacements are
atomic and fsynced; the preceding credential file is retained as `creds.json.backup`.
The heartbeat is refreshed only while connected. `store/whatsapp-collector/last-upload`
records successful archive uploads, not merely a running process.

Stop the service, then run `./node_modules/.bin/tsx tools/whatsapp_collector.ts pair`
from `/home/assistant/nanoclaw` in an interactive SSH terminal. Scan the QR with
WhatsApp's Linked devices screen. Pairing preserves the old auth directory under
a timestamped `.prelink-` name. After credentials are saved, pairing resets the failed service and starts the collector automatically. A protected QR PNG is also written for viewers that cannot display terminal QR codes.
Verify a fresh heartbeat and an archive upload from an allowlisted group; reconnecting
does not guarantee recovery of messages missed during the outage.

### Conversation memory controls

The Personal Assistant supports `/memory`, `/memory check`, `/memory refresh`,
and `/memory forget <exact-relative-path>`. These are handled conversationally
by the assistant: `/memory` shows a concise inventory, `check` reports stale or
contradictory entries, `refresh` reviews recent conversations, and `forget`
removes only the exact requested memory file after confirmation. The nightly
02:00 UTC pass also updates `memory/review.md` with its freshness and conflict
check. Time-sensitive memory uses `as_of` and optional `review_after` metadata.

## Assistant operations (October 4, 2026)

Telegram supports `/work`, `/projects`, `/meetings`, `/research`, `/improve`,
`/refine`, `/mail`, and `/memory`. These invoke agent workflows; `/refine` saves
owner preferences in `groups/personal-assistant/work/state.json` and can update
native schedules. Every request/run rereads preferences and active procedures.
Examples: `/projects Prepare a decision on our search tools`, `/refine Give me
prepared actions instead of generic status reports`, `/improve rollback the
WhatsApp freshness procedure`, `/mail check the inbox`.

The assistant-operations skill ships in the personal-assistant template and the
live group's canonical skill store. Atomic workboard writes preserve existing
fields and serialize writers; a crashed writer's lock requires inspection and
manual recovery. Commitments require explicit owner instruction and a source.
Local capability candidates need observed failure, acceptance cases, a passing
baseline comparison and a real bounded evidence file. Promotion records the
previous version; a reported regression rolls back immediately. This is a
quality gate inside the agent workspace. The host's approval and permission
controls remain the security boundary.

Native scheduled series (UTC; owner timezone Asia/Jerusalem):

| Series | Schedule | Behavior |
|---|---|---|
| project-follow-through-6491 | 07:00, 14:00 daily | Gated on due projects/research/explicit commitments; advance a useful action |
| meeting-preparation-9940 | Every 30 minutes | Calendar gate; upcoming 90 minutes, skip cancelled/declined/prepared events |
| capability-improvement-7515 | 02:15 daily | Gated on real improvement backlog; test, promote and monitor |
| agent-inbox-review-ecb8 | 07:30, 15:30 daily | Read latest mail; deduplicate useful notifications; silent when nothing new |

The weekday brief now reads work records and prepares next actions. The existing
nightly memory job now audits three retrieval examples and reconciles a dated
recovery handoff; it still cannot change tools, policy, credentials or skills.
The live schedule index is `work/schedules.json`; use native task commands to
change/pause/resume jobs from Telegram. Empty gates spend no model tokens; inbox
checks currently make two model invocations/day. Exact-time commitments should
also create a native one-shot reminder.

Dedicated inbox: the agent-owned address configured for this installation. Its API key is
host-only in protected `config/agentmail/account.json`, never mounted into an
agent. `assistant_mail_read` returns untrusted mail data. `assistant_mail_send`
freezes one recipient, subject and body in the native approval record and sends
only after approval. No automatic registrations, paid plans or external email
sends were performed by the rollout. Provider keys are not stored in chat or
skills. Tavily/Gemini research is an artifact; those integrations are not enabled.

`run_experiment` accepts bounded source text, writes a fresh host-owned temporary
directory, and mounts that source snapshot read-only in Docker: network disabled, no credentials,
no other workspace mounts, read-only root, dropped capabilities, non-root user,
512 MB/one CPU/128 PIDs, writable temporary space capped at 64 MB, 120-second timeout and output caps. Temporary sources are
removed after success/failure. Return is asynchronous; the agent must wait for
host evidence before claiming pass. Installed Node/Bun/bash/sh need no new deps.

Verification evidence: `work/verification.json` records preferences recalled in
a fresh agent session and successful inbox read; `labs/runtime-isolation-check/`
contains a real host trial checking absent API keys, absent owner workspace and
blocked outbound network. Native delivery logs confirmed Telegram/Slack messages.
The first promoted procedure, WhatsApp freshness, passed 10 synthetic cases
versus 2 for the newest-message-only draft baseline. This does not establish
capture completeness for messages missed before the relink.

### OneCLI OAuth refresh repair

Live OneCLI remains the existing all-in-one deployment, with the upstream OAuth
`client_id` fix backported into its gateway binary. Image:
`onecli:1.41.0-refresh-fix`; original image and protected database/config backups
are retained. `tools/build_onecli_refresh_fix.py` pins the inspected upstream
commit and builder/base image digests; it copies no credentials into the build.
The running gateway binary and container health were checked; the Codex models
endpoint returned HTTP 200 afterward. A real forced grant rotation has not been
performed; the form fix is taken from released upstream code. OAuth grants can
still require reauthorization if revoked or concurrently reused by another client.

The v2.7 release uses separate API/web/gateway images; its old all-in-one tag is
unavailable. Its schema/topology migration was not applied. The compose image is
pinned to the backport until a separately planned upgrade. For rollback, restore
the backed-up compose file and run `docker compose up -d --no-deps onecli`; no
schema migration was introduced by this repair.

### Autonomous provider signup

Provider account registration requires an explicit owner request and the configured agent-owned inbox. Installation templates do not grant standing permission to create accounts. The assistant must attempt the actual browser flow and its own inbox verification before reporting a human requirement. Google account creation may use the existing agent email; owner identity details must not be invented or reused. Billing and paid trials remain disabled. Generated keys go only into protected onboarding files for host-managed import, never chat. Signup results and concrete blockers are saved under `work/provider-onboarding/`; an unconnected provider remains unconnected until an authenticated API request succeeds.

## Delivery evidence and account-free research

The existing five-minute host health timer invokes scripts/report-watchdog.py.
The five daily/weekly report series are checked using task-correlated outbound
rows and nonempty confirmed Telegram/Slack platform receipt IDs. Current-day
terminal runs with zero delivered channels may retry once after 15 minutes;
partial delivery alerts without duplicating the report. Alerts fire after 30
minutes, or 30 minutes after retry, with receipts persisted immediately. Daily
slots aggregate original/manual/retry runs so a confirmed same-day recovery
satisfies that report day. Older missing days remain visible for 48 hours and
alert without queueing an incorrect current-day catch-up. Direct Telegram
alerts use the host bot credential and do not need working model OAuth.
work/report-delivery.json lets owner Telegram refinements choose telegram and/or
slack per series, or explicitly disable monitoring.

Provider errors, unfinished closed streams, and result dispatch/log errors now
produce failed task acknowledgments; host synchronization preserves failures.
Successful acknowledgment follows result dispatch/log writing. Native recurrence
retains its existing backoff. Historical counters were not broadly rewritten.

The public-research helper provides bounded Hacker News discovery and Crossref
scholarly metadata without accounts/keys. Original-source verification is still
required. The completed account-free-research project saved real API results and
a decision under work/artifacts/account-free-research/ and sent it to Telegram.
Two independent fresh-session probes recalled all four owner preferences and the
active WhatsApp procedure version. Host-scored proof is saved as
work/artifacts/memory-evaluation-2026-10-04.json. This verifies retrieval and
proposed behavior, not every future action.

## Human browser handoff

Telegram /connect handoff tavily prepares the blocked step; /connect continue
tavily resumes it. Gemini is supported within its existing scoped authorization.
The agent records a 25-minute handoff in work/browser-handoff.json and leaves
its browser open. Open Agent Browser.command in the Mac workspace runs
scripts/browser-handoff.py: only 127.0.0.1:4848 is bound, the prepared PA container
identity is verified, foreign origins/hosts are rejected, and its loopback
dashboard is forwarded over SSH. No public browser endpoint is created. The
helper expires with the handoff and requires this Mac's SSH access; phone-only
remote takeover is not enabled. An expired container needs a fresh handoff from
the saved profile. Human takeover does not guarantee provider browser acceptance
or relax Google identity requirements.

## Drive video and Telegram capability development

`run_agy_media` accepts exactly one inbox attachment path or owner-selected Drive `file_id`. The host reader streams the selected video into a private temporary directory, enforces 256 MB before and during download, rejects folders/shortcuts, verifies stable source metadata and the video container, and uses ffprobe to validate a real video stream. Credentials and unrelated group files are excluded from the media workspace. Source ID/version, processed size, duration and compression state accompany the result; temporary media is removed on success and failure.

AGY's binary reader caps files at 100 MB. Videos above 90 MB are reencoded below that threshold with a 960×540 maximum frame size, 5 fps and audio retained. This changes fidelity; analysis must state uncertainty. Extremely long recordings that cannot fit the bitrate budget need a selected interval via `start_seconds` and `duration_seconds`; the host clips it and preserves the source timestamp offset. The host needs ffmpeg/ffprobe. The runner's media CLI timeout is 18 minutes to cover the bounded download, preprocessing and worker phases; ordinary CLI requests retain 30 seconds.

Telegram `/models` and both AGY tools accept Gemini 4 Argon IDs. Provider entitlement is independent of the local allowlist; on October 14 the authenticated AGY 1.3.5 catalog still listed Flash 3.8 and did not expose Argon. Do not claim Argon runs until the account returns success.

For owner-requested repairs, the bounded maintenance workflow supports integration TypeScript, scheduling and selected mailbox/delivery files, Python Drive helpers/tests and the collector. The controller, supervisor, approval internals, credentials, config and guards remain excluded from agent edits. Drafts contain up to 20 files / 512 KiB and 10 relevant tests. The complete immutable diff is available through `host-change-review`; native approval binds its digest, summary, paths and test definition. Node and Python tests run in separate credential-free, network-disabled containers. Build `nanoclaw-maintenance-python:3.13` using `container/maintenance-python.Dockerfile` before Python staging.

`host-change-apply` rechecks drift/tests and builds, then a separate systemd-run supervisor restarts services and verifies a new host PID, real CLI readiness, relevant integration checks and a fresh collector heartbeat. Only stable health records `applied.json`. Failed health restores the previous source/build and verifies recovery; failed recovery remains failed. `host-change-status` exposes built/restarting/healthy/rolling_back/rolled_back/conflict/failed independently of conversation state. The rollout of the protected controller/supervisor requires an owner-approved operator bootstrap; the existing controller cannot upgrade itself.

`assistant-diagnostics` exposes service state, own pending approval receipts/failures, work evidence freshness and WhatsApp per-group coverage/ingestion lag without credential payloads. `approval-delivery-retry` retries the same pending decision ID; pending/unverified/delivered remain distinct. Capture checkpoints start when the feature activates; retained archive IDs track ingestion progress, while older backlog and never-captured history remain unknown. Empty groups are unverified, not inactive.

Tasks accept an explicit IANA timezone in their content envelope; existing tasks without one retain the group default. `tasks update --timezone` recomputes the next cron occurrence unless process_after is explicitly supplied. Cancellation persists a host-owned session marker, blocks rearming and queued delivery/CLI actions, and aborts active AGY requests. Already sent or in-flight external effects cannot be rolled back.

`agy-models` reads the authenticated account catalog. Explicit model IDs are checked before downloading or preprocessing video; unavailable IDs fail without selecting a replacement. On October 18 the live catalog listed Argon high/medium/low; that confirms entitlement discovery, not successful video inference.
