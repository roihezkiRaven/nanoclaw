# Personal Assistant template

This template creates the single-owner policy and a paused nightly memory task.
It deliberately contains no provider, channel, token, Drive, GitHub, or backup
configuration. Configure those interactively on the VPS, then stamp it with:

```bash
ncl groups create --template personal-assistant --name "Personal Assistant" --timezone UTC
```

Resume the generated nightly task only after verifying the group and its owner
wire-up. Restamping updates policy/task definitions but preserves memory and
channel wiring.


The assistant-operations skill adds durable projects, explicit commitments,
meeting prep, research trials, versioned procedure improvements and Telegram
refinements. Native host tools provide credential-isolated experiments and an
approval-protected agent mailbox. Configure the dedicated mailbox on the host;
keys are never part of this template. Live recurring jobs and evidence are
documented in `docs/personal-assistant/operations.md`; new deployments should configure native jobs after owner/channel wiring is
verified. The template nightly task initially remains paused.

## Verified research and browser handoff

Assistant operations includes account-free Hacker News/Crossref helpers, with
original-source verification and dated evidence. Host monitoring checks actual
correlated Telegram/Slack receipts, retries a missing read-only daily report
once, and alerts directly through Telegram. Owner /refine destination changes
update report-delivery settings as well as task prompts.

Use /connect handoff tavily and /connect continue tavily for the named approved
signup. The Mac Open Agent Browser.command helper forwards that same browser
through private SSH/loopback access for the human step. Handoffs expire and need
this Mac's SSH access; provider acceptance and identity gates can remain blocked.
