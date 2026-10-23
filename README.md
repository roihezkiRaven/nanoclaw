# PersonalAssist

A personal assistant with shared Telegram and Slack conversations, scheduled work,
and separate knowledge pipelines for meeting notes and allow-listed WhatsApp groups.
This repository contains the application, agent templates, host tools, deployment
units, and tests for that system.

## Agents and knowledge

| Agent | Responsibility |
| --- | --- |
| Personal Assistant | Owner conversations, research, meeting preparation, commitments, and approved tool use. Reads the published knowledge graph. |
| Timeless Brain | Turns eligible meeting notes into dated project status, tasks, decisions, and a compact synthesis. |
| WhatsApp Brain | Maintains source-grounded daily digests and AI-learning summaries for explicitly allowed groups. |

The knowledge bases have separate source policies and publication checks.
Timeless excludes transcripts, recordings, media, and WhatsApp material. WhatsApp
learning stays within its own graph. Each source is checkpointed by file ID and
revision; material project updates must reach canonical project pages.

```text
Timeless notes → project/task/decision pages → Timeless synthesis → Drive mirror
Allowed WhatsApp groups → daily digests → WhatsApp synthesis → Drive mirror
                                           ↓
                                Personal Assistant reads
```

Publication validates metadata, provenance, links, and knowledge boundaries.
Unchanged files keep their Drive modification time. Review dates and evidence
dates are distinct; a synced file is not proof that every source claim is current.
Ingestion runs on a schedule, with explicit replay for recovery.

## Start here

- [Operations](docs/personal-assistant/operations.md): integrations, monitoring, schedules, recovery, and private configuration.
- [Knowledge pipelines](docs/personal-assistant/knowledge-base.md): sources, graphs, checkpoints, and Drive publication.
- [Approval boundaries](docs/personal-assistant/autonomy.md): which actions require owner approval.
- [Deployment](deploy/hetzner/README.md): provision a host and configure the assistant.
- [Agent template](templates/personal-assistant/README.md): create or restamp the owner-facing assistant.
- [Updates](docs/personal-assistant/updates.md): review and deploy changes to an existing installation.
- [Documentation index](docs/README.md): architecture, runtime, migrations, and reference material.

## Development

Use Node.js 22 or newer, pnpm, and Docker for container execution. Bun runs the
agent-runner tests; Python 3 runs the knowledge validator and host helpers.

```bash
git clone https://github.com/roihezkiRaven/nanoclaw.git personalassist
cd personalassist
pnpm install --frozen-lockfile
pnpm run typecheck
pnpm test
python3 scripts/validate_knowledge_wiki_test.py
```

Run the container suite from its package directory:

```bash
cd container/agent-runner
bun install --frozen-lockfile
bun test
```

Deployment and external integrations require separate host configuration. The
source checkout does not contain a configured account or a live knowledge base.
Follow the deployment and operations guides before starting services.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/` | Host routing, delivery, scheduling, approvals, channels, and personal-assistant tools. |
| `container/agent-runner/` | Agent execution, providers, session mailbox, and tool transport. |
| `templates/personal-assistant/` | Reusable assistant instructions, tools, and skills. |
| `assets/timeless-brain/`, `assets/whatsapp-brain/` | Knowledge-maintainer instructions and seed graphs. |
| `tools/`, `scripts/` | Drive helpers, ingestion/publication checks, monitoring, and maintenance. |
| `deploy/` | Host provisioning and systemd service/timer definitions. |
| `docs/personal-assistant/` | Operational documentation for this application. |

## Private state

Credentials, OAuth tokens, owner identities, chats, knowledge content, databases,
logs, and recovery archives stay outside Git. Runtime directories such as
`config/`, `groups/`, `data/`, and `store/` are ignored. Working notes under
`claude_docs/` are private except the intentionally tracked roadmap folder.

Keep real deployment values out of templates and issue reports. Use
`config-examples/` for synthetic configuration shapes. Reviewed source changes
should be committed, secret-scanned, and pushed; private runtime state needs its
own protected backups.

## Foundation and license

PersonalAssist builds on [NanoClaw](https://github.com/nanocoai/nanoclaw). Runtime
identifiers including `nanoclaw.sh`, `ncl`, `NANOCLAW_*`, and existing deployment
paths retain their compatibility names. Technical and migration references may
use the engine's original terminology.

The original MIT license and copyright notice are retained in [LICENSE](LICENSE).
Historical upstream credits are preserved in [CONTRIBUTORS.md](CONTRIBUTORS.md).
See [CONTRIBUTING.md](CONTRIBUTING.md) for this repository's workflow.
