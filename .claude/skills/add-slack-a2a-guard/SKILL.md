---
name: add-slack-a2a-guard
description: Compatibility marker for the Slack bot-inbound guard installed by add-slack.
---

# Slack A2A guard compatibility

The Slack bot-inbound guard is installed and refreshed by `/add-slack` from the
channels registry. This instruction-only skill keeps older installs that record
`add-slack-a2a-guard` in their installed-skill recipe updateable.

Verify that `src/channels/slack-a2a-guard.ts` exports
`setBotInboundPolicy`. Do not copy files, change permissions, or add a second
registration import. If the export is missing, stop and re-apply `/add-slack`
from a channels revision that provides the guard.
