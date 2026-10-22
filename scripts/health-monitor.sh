#!/usr/bin/env bash
set -euo pipefail

root=/home/assistant/nanoclaw
group_id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["group_id"])' "$root/config/report-watchdog.json")
disabled="$root/groups/personal-assistant/health-monitor.disabled"
state_dir="$root/data/health-monitor"
state_file="$state_dir/last-alert"
mkdir -p "$state_dir"

if [[ -e "$disabled" ]]; then
  exit 0
fi

issues=()
python3 "$root/scripts/report-watchdog.py" >/dev/null || issues+=(report-delivery-monitor)
systemctl is-active --quiet docker || issues+=(docker)
systemctl --user is-active --quiet nanoclaw-v2-fc17183a.service || issues+=(nanoclaw)
systemctl --user is-active --quiet gdrive-broker.service || issues+=(gdrive-broker)
if ! systemctl --user is-active --quiet whatsapp-collector.service || ! find "$root/store/whatsapp-collector/heartbeat" -mmin -3 -print -quit 2>/dev/null | grep -q .; then
  issues+=(whatsapp-collector)
fi
"$root/.venv-gdrive/bin/python" "$root/tools/gdrive_assistant.py" reader check >/dev/null \
  || issues+=(drive-reader)
"$root/.venv-gdrive/bin/python" "$root/tools/gdrive_assistant.py" writer check >/dev/null \
  || issues+=(drive-writer)
"$root/.venv-gdrive/bin/python" "$root/tools/gdrive_assistant.py" calendar check >/dev/null \
  || issues+=(google-calendar)
python3 "$root/scripts/validate-knowledge-wiki.py" "$root/data/timeless-wiki" >/dev/null \
  || issues+=(knowledge-wiki)
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
if [[ ",$summary," == *,gdrive-broker,* ]]; then
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
