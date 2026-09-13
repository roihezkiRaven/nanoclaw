#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "Run as root on a fresh Ubuntu 24.04 VPS." >&2
  exit 1
fi

SSH_PORT="${SSH_PORT:-22}"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y upgrade
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl git build-essential python3-venv gh docker.io ufw unattended-upgrades

id -u assistant >/dev/null 2>&1 || useradd --create-home --shell /bin/bash --groups sudo,docker assistant
usermod -aG sudo,docker assistant
systemctl enable --now docker unattended-upgrades

ufw default deny incoming
ufw default allow outgoing
ufw allow "${SSH_PORT}/tcp"
ufw --force enable

runuser -u assistant -- docker run --rm hello-world >/dev/null
echo "Bootstrap complete. Continue as assistant with deploy/hetzner/README.md."
