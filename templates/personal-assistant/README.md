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
