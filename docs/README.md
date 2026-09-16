# NanoClaw documentation

This directory is organized by how the system is used. The former top-level
paths remain as compatibility symlinks.

## Personal assistant

- [Operations](personal-assistant/operations.md) — deployed channels, retained data, schedules, and recovery.
- [Autonomy](personal-assistant/autonomy.md) — chat-controlled changes and approval boundaries.
- [Knowledge base](personal-assistant/knowledge-base.md) — OKF graph, Timeless notes, WhatsApp digests, and Drive mirrors.
- [Updates](personal-assistant/updates.md) — personal-fork drift checks and transactional VPS upgrades.
- [Gemini](personal-assistant/gemini.md) — compliant use of the separate Gemini subscription.

## Guide

- [Setup flow](guide/setup-flow.md) · [setup wiring](guide/setup-wiring.md)
- [Build and runtime](guide/build-and-runtime.md) · [scheduled tasks](guide/scheduled-tasks.md)
- [Customizing](guide/customizing.md) · [requirements](guide/REQUIREMENTS.md)
- [Community portal](guide/community-portal.md) · [Ollama](guide/ollama.md)

## Architecture

- [Architecture](architecture/architecture.md) · [diagram](architecture/architecture-diagram.md)
- [Database overview](architecture/db.md) · [central DB](architecture/db-central.md) · [session DB](architecture/db-session.md)
- [Isolation](architecture/isolation-model.md) · [memory](architecture/memory.md) · [historical v1 spec](architecture/SPEC.md)

## Security

- [Security model](security/SECURITY.md) · [hardened images](security/hardened-image.md)

## Skills

- [Skills model](skills/skills-model.md) · [authoring guidelines](skills/skill-guidelines.md)
- [Directive format](skills/skill-directives.md) · [engine seam](skills/skill-engine-seam.md) · [templates](skills/templates.md)

## Migrations

- [Upgrade recovery](migrations/upgrade-recovery.md) · [v1 to v2](migrations/v1-to-v2-changes.md)
- [Provider](migrations/provider-migration.md) · [host lifecycle](migrations/host-lifecycle-migration.md)
- [Task](migrations/ncl-tasks-migration.md) · [mailbox](migrations/agent-mailbox-seam-migration.md)
- [Database async](migrations/central-db-async-migration.md) · [development](migrations/migration-dev.md)

## Reference

- [API details](reference/api-details.md) · [agent runner](reference/agent-runner-details.md)
- [SDK deep dive](reference/SDK_DEEP_DIVE.md) · [OneCLI upgrades](reference/onecli-upgrades.md)
- [Fork maintenance](reference/BRANCH-FORK-MAINTENANCE.md)

The official product documentation is at [docs.nanoclaw.dev](https://docs.nanoclaw.dev).
