---
name: assistant-control
description: Manage the owner's reminders, briefings, task schedules, and health-monitor pause state through chat.
---

# Assistant Control

Use this skill when the owner asks to change a reminder, briefing, recurring task, model setting, or health-monitor state.

## Schedules

Use native `ncl tasks` commands to create, list, update, pause, resume, run, or cancel owner-requested schedules. State the task ID, cron schedule, installation timezone, delivery destination, and whether it is active in the response.

- Never create a frequent recurring task without explaining expected model usage and getting confirmation.
- Scheduled messages must be concise and delivered to the owner's approved Telegram and/or Slack channel.
- If an instruction is ambiguous, ask for a time, timezone, recurrence, and destination instead of guessing.

## Health monitor

The host checks NanoClaw, Docker, the Drive broker, and disk space every five minutes. The owner can pause or resume alerts without host access:

```bash
# Pause alerts
touch /workspace/agent/health-monitor.disabled

# Resume alerts
rm -f /workspace/agent/health-monitor.disabled
```

Confirm the resulting state. Do not alter the host monitor implementation, service, timer, credentials, or alert destinations.
