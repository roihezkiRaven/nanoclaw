# Assistant autonomy and approvals

The personal assistant is intentionally useful from Telegram and Slack while
keeping host authority narrow.

## Allowed from chat

The owner may ask the assistant to create, update, pause, resume, run, cancel,
or inspect native `ncl tasks`. The assistant must report the task ID, schedule,
timezone, destination, model, expected usage, and active state.

It may also create a reversible user-level skill or workflow in the agent
workspace. Each generated skill must document inputs, outputs, data sources,
permissions, dry-run behavior, retry policy, and disable/rollback commands. The
assistant updates the skills index and records an audit entry.

## Approval required

Credentials, OAuth, mounts, channel permissions, Docker, systemd, firewall,
backups, Git pull/push, provider changes, service restarts, destructive writes,
and new external recipients require explicit owner approval of the exact scope.

The container must never gain arbitrary host shell access as a shortcut. Host
operations go through validated NanoClaw/OneCLI interfaces and fail closed when
an operation is outside the allowlist.

## Safe workflow

1. Explain the requested change and its authority boundary.
2. Validate names, schedule, timezone, destination, and source scope.
3. Dry-run where possible.
4. Apply only the permitted change.
5. Return a success message with IDs and rollback instructions.

Frequent recurring tasks must include a cost explanation. Failed tasks use
native retry/backoff and are paused after repeated failures rather than silently
creating duplicate work.
