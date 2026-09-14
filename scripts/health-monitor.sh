#!/usr/bin/env bash
set -euo pipefail

root=/home/assistant/nanoclaw
group_id=ag-2a8d9d8e-dec3-4a12-9a27-ebcf4945661a
disabled="$root/groups/personal-assistant/health-monitor.disabled"
state_dir="$root/data/health-monitor"
state_file="$state_dir/last-alert"
mkdir -p "$state_dir"

if [[ -e "$disabled" ]]; then
  exit 0
fi

issues=()
systemctl is-active --quiet docker || issues+=(docker)
systemctl --user is-active --quiet nanoclaw-v2-fc17183a.service || issues+=(nanoclaw)
systemctl --user is-active --quiet gdrive-broker.service || issues+=(gdrive-broker)
if ! systemctl --user is-active --quiet whatsapp-collector.service || ! find "$root/store/whatsapp-collector/heartbeat" -mmin -3 -print -quit 2>/dev/null | grep -q .; then
  issues+=(whatsapp-collector)
fi
curl --noproxy '*' --connect-timeout 3 --max-time 5 -fsS -o /dev/null \
  -X POST http://172.17.0.1:8765/ -H 'content-type: application/json' \
  --data '{"action":"calendar","limit":1}' || issues+=(gdrive-api)
disk_used=$(df -P / | awk 'NR == 2 { gsub(/%/, "", $5); print $5 }')
if [[ "${disk_used:-100}" -ge 85 ]]; then
  issues+=(disk-"$disk_used"-percent)
fi

if ((${#issues[@]} == 0)); then
  rm -f "$state_file"
  exit 0
fi

summary=$(IFS=,; echo "${issues[*]}")
if [[ -f "$state_file" && $(<"$state_file") == "$summary" ]]; then
  exit 0
fi
printf '%s' "$summary" >"$state_file"

if [[ ",$summary," == *,nanoclaw,* ]]; then
  systemctl --user restart nanoclaw-v2-fc17183a.service || true
fi
if [[ ",$summary," == *,gdrive-broker,* || ",$summary," == *,gdrive-api,* ]]; then
  systemctl --user restart gdrive-broker.service || true
fi
if [[ ",$summary," == *,whatsapp-collector,* ]]; then
  systemctl --user restart whatsapp-collector.service || true
fi

if "$root/node_modules/.bin/tsx" "$root/src/cli/client.ts" tasks create \
  --group "$group_id" --name "health-alert-$(date -u +%Y%m%d%H%M)" \
  --process-after "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --prompt "Health monitor detected: $summary. Verify the affected service with the available read-only tools, then send the owner a concise alert to both approved Telegram and Slack channels. Do not expose credentials or attempt policy changes." >/dev/null 2>&1; then
  exit 0
fi

logger -t nanoclaw-health-monitor "Detected $summary; NanoClaw task delivery unavailable"
