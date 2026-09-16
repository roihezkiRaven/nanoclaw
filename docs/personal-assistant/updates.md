# VPS updates

The VPS deploys from the personal fork configured as `origin`; the official
NanoClaw repository is an explicit upstream source for review and synchronization.
There is no automatic production pull or GitHub-triggered cutover.

## Normal path

An update checker may fetch remote metadata read-only and notify the owner when
the VPS is behind. “Prepare update” stages the change in an isolated worktree,
refreshes installed skills, installs frozen dependencies, builds, and runs tests.

The assistant presents changed files, migrations, requirements, snapshot/backup
state, and the rollback point. Cutover occurs only after owner approval. The
transaction stops the detected service, drains this install's containers,
snapshots mutable state, restarts, and verifies the process, CLI socket, native
groups, Telegram, Slack, Drive broker, collectors, and timers.

Build or health failure restores the previous Git tree and mutable-state
snapshot, rebuilds the previous image, restarts it, and reports the failed check.

Secrets remain in host-only protected stores and are never committed or mounted
into agent containers.

The read-only checker is `scripts/check-fork-update.ts`; the optional systemd
units are `deploy/fork-update-check.service` and
`deploy/fork-update-check.timer`. The timer only logs JSON drift status. The
owner-facing assistant can turn that status into a Telegram notification without
granting the timer any update authority.
