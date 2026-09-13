# Hetzner deployment

Run `sudo SSH_PORT=22 bash deploy/hetzner/bootstrap.sh` on a fresh Ubuntu 24.04
server. Change `SSH_PORT` if SSH does not use port 22. The script creates the
`assistant` account, enables Docker, limits inbound traffic to SSH, and verifies
that the account can run Docker without root.

Then log in as `assistant` and deploy the personal fork:

```bash
git clone https://github.com/roihezkiRaven/nanoclaw.git ~/nanoclaw
cd ~/nanoclaw
bash nanoclaw.sh
```

In the installer select the local `personal-assistant` template, Codex as the
provider, and UTC as the group timezone so the nightly memory task fires at
02:00 UTC. Complete Codex's ChatGPT device login in your browser. Do not paste
subscription credentials into files or chat.

After setup, run the shipped `/add-slack` and `/add-telegram` skills from the
host coding session. Use Slack Socket Mode and pair only your Telegram DM. Seed
only your Slack member ID and Telegram user ID as owner identities. Wire both
DMs to the Personal Assistant group with `session_mode: shared`, preserving
separate transcripts while sharing workspace memory.

Do not enable the nightly task until Drive, GitHub approvals, and backup
integrations are installed and tested. Those integrations require operator-owned
OAuth/App credentials and cannot safely be provisioned from this repository.

Before going live, commit the skill-applied Codex/Slack/Telegram source changes
to this personal fork, verify the generated user systemd unit survives reboot,
and run the smoke checks in the project README.
