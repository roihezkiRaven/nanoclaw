#!/usr/bin/env python3
"""Check actual report receipts; retry only bounded read-only brief jobs."""
import datetime as dt
import json
import os
import re
from pathlib import Path
import sqlite3
import subprocess
import urllib.request

GROUP = ""
REPORTS = set()
DESTINATIONS = {}


def configure(root):
    """Load deployment identities from host-only configuration, never Git."""
    global GROUP, REPORTS, DESTINATIONS
    settings = json.loads((root / "config/report-watchdog.json").read_text())
    group, reports, destinations = settings["group_id"], settings["reports"], settings["platform_destinations"]
    if not isinstance(group, str) or not group.startswith("ag-"):
        raise ValueError("Invalid watchdog group")
    if not isinstance(reports, list) or not reports or any(not isinstance(x, str) or not x for x in reports):
        raise ValueError("Invalid watchdog report series")
    if not isinstance(destinations, dict) or not set(destinations) <= {"telegram", "slack"}:
        raise ValueError("Invalid watchdog destinations")
    if not isinstance(destinations.get("telegram"), str) or not re.fullmatch(r"telegram:-?\d+", destinations["telegram"]):
        raise ValueError("Watchdog requires the configured owner Telegram chat")
    if "slack" in destinations and (not isinstance(destinations["slack"], str) or not destinations["slack"].startswith("slack:C")):
        raise ValueError("Invalid watchdog Slack destination")
    GROUP, REPORTS, DESTINATIONS = group, set(reports), destinations


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=dt.timezone.utc).timestamp()


def read_db(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as output:
        os.chmod(temporary, 0o600)
        json.dump(state, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def telegram_alert(root, text):
    """Send fixed-owner alerts without depending on the model or its OAuth grant."""
    token = ""
    for line in (root / ".env").read_text().splitlines():
        key, _, value = line.strip().partition("=")
        if key == "TELEGRAM_BOT_TOKEN":
            token = value.strip().strip("\"'")
    if not token:
        raise RuntimeError("Telegram alert credential unavailable")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": int(DESTINATIONS["telegram"].split(":", 1)[1]), "text": text[:2800]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
        if not result.get("ok"):
            raise RuntimeError()
        return result["result"]["message_id"]
    except Exception:
        raise RuntimeError("Telegram alert delivery failed; no credential details logged") from None


def receipt_channels(inbound, outbound, since, run_ids):
    receipts = {r["message_out_id"]: r for r in inbound.execute(
        "SELECT * FROM delivered WHERE status='delivered' AND platform_message_id IS NOT NULL AND trim(platform_message_id) <> ''"
    )}
    channels = set()
    for row in outbound.execute("SELECT * FROM messages_out WHERE kind='chat'"):
        if row["id"] not in receipts or row["in_reply_to"] not in run_ids or timestamp(row["timestamp"]) < since:
            continue
        text = json.loads(row["content"]).get("text", "").strip()
        if text and not text.startswith("Error:") and DESTINATIONS.get(row["channel_type"]) == row["platform_id"]:
            channels.add(row["channel_type"])
    return channels


def inspect_slot(inbound, outbound, runs, required, state, now, retry, alert, persist):
    run = runs[-1]
    series = run["series_id"]
    since = min(timestamp(r["process_after"]) for r in runs)
    day = dt.datetime.fromtimestamp(since, dt.timezone.utc).date()
    key = f"{series}:{day}"
    record = state.setdefault("runs", {}).setdefault(key, {})
    channels = receipt_channels(inbound, outbound, since, {r["id"] for r in runs})
    missing = required - channels
    record["observed_run_ids"] = [r["id"] for r in runs]
    if not missing:
        record["delivered"] = sorted(channels)
        persist()
        return []
    current_day = dt.datetime.fromtimestamp(now, dt.timezone.utc).date()
    if day == current_day and not channels and not record.get("retried") and run["status"] in ("failed", "completed"):
        return retry_slot(record, series, now, retry, persist)
    if now - record.get("retry_at", since) < 1800 or record.get("alert_message_id"):
        return []
    return alert_slot(record, run, missing, alert, persist, day)


def retry_slot(record, series, now, retry, persist):
    record.update(retried=True, retry_at=now)
    persist()
    try:
        retry(series)
    except Exception as error:
        record["retry_error"] = type(error).__name__
        persist()
    return [{"series": series, "action": "retry"}]


def alert_slot(record, run, missing, alert, persist, day):
    record["alert_message_id"] = alert(
        f"Report delivery problem: {run['series_id']} for {day}. Missing confirmed receipt: {', '.join(sorted(missing))}. "
        f"Run status: {run['status']}. {'One retry was attempted.' if record.get('retried') else 'No duplicate report was queued.'} "
        "The completed counter does not prove delivery."
    )
    persist()
    return [{"series": run["series_id"], "action": "alert", "missing": sorted(missing)}]


def due_slots(runs, state, now):
    slots = {}
    for run in reversed(runs):
        if run["series_id"] not in REPORTS or run["status"] in ("cancelled", "paused"):
            continue
        due = timestamp(run["process_after"])
        if max(state["started_at"], now - 172800) <= due <= now - 900:
            day = dt.datetime.fromtimestamp(due, dt.timezone.utc).date()
            slots.setdefault((run["series_id"], day), []).append(run)
    return slots.values()


def inspect_session(folder, settings, state, now, retry, alert, persist):
    events = []
    with read_db(folder / "inbound.db") as inbound, read_db(folder / "outbound.db") as outbound:
        runs = inbound.execute("SELECT * FROM messages_in WHERE kind='task' AND process_after IS NOT NULL ORDER BY process_after DESC").fetchall()
        for slot in due_slots(runs, state, now):
            series = slot[0]["series_id"]
            required = set(settings.get("destinations", {}).get(series, ["telegram", "slack"]))
            if not required or not required <= set(DESTINATIONS):
                raise ValueError("Report destinations must be telegram and/or slack")
            events += inspect_slot(inbound, outbound, slot, required, state, now, retry, alert, persist)
    return events


def inspect(root, state, now, retry, alert, persist=lambda: None):
    settings_path = root / "groups/personal-assistant/work/report-delivery.json"
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    if settings.get("disabled") is True:
        return []
    with read_db(root / "data/v2.db") as central:
        sessions = central.execute("SELECT id FROM sessions WHERE agent_group_id=? AND thread_id LIKE 'system:tasks:%'", (GROUP,)).fetchall()
    events = []
    for session in sessions:
        folder = root / "data/v2-sessions" / GROUP / session["id"]
        if (folder / "inbound.db").exists() and (folder / "outbound.db").exists():
            events += inspect_session(folder, settings, state, now, retry, alert, persist)
    return events


def sync_properties(unit):
    result = subprocess.run(["systemctl", "--user", "show", unit, "-p", "Result", "-p", "ActiveState", "-p", "ExecMainExitTimestamp"],
                            check=True, capture_output=True, text=True, timeout=10,
                            env={**os.environ, "TZ": "UTC", "LC_ALL": "C"})
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def retry_sync(unit):
    subprocess.run(["systemctl", "--user", "start", "--no-block", unit],
                   check=True, capture_output=True, timeout=10)


def inspect_knowledge_sync(state, now, alert, persist, properties=sync_properties, retry=retry_sync, publication=lambda unit: {}, units=("knowledge-wiki-sync.service", "whatsapp-wiki-sync.service")):
    """Detect failed/stale mirrors independently of model availability."""
    events = []
    day = dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()
    for unit in units:
        info = properties(unit)
        if info.get("ActiveState") in ("active", "activating"):
            continue
        stamp = info.get("ExecMainExitTimestamp", "")
        last = dt.datetime.strptime(stamp, "%a %Y-%m-%d %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc).timestamp() if stamp else state["started_at"]
        record = state.setdefault("knowledge_sync", {}).setdefault(unit, {})
        if info.get("Result") == "success" and now - last <= 36 * 3600:
            events += inspect_publication(unit, record, day, now, publication(unit), alert, persist)
            continue
        events += recover_sync(unit, record, day, alert, persist, retry)
    return events


def inspect_publication(unit, record, day, now, status, alert, persist):
    if status.get('mode') == 'degraded':
        return alert_degraded(unit, record, day, status, alert, persist)
    oldest = status.get('oldest_pending_since', status.get('oldest_pending_revision'))
    if oldest and now - timestamp(oldest) > 26 * 3600:
        return alert_source_lag(unit, record, day, alert, persist)
    record.clear()
    return []


def alert_degraded(unit, record, day, status, alert, persist):
    if record.get("degraded_alert_day") == day:
        return []
    stamp = status.get("brain_snapshot_at", "unknown")
    message = f"Knowledge publishing degraded: {unit} published validated source pages with last-good synthesis from {stamp}. The rejected synthesis is preserved for repair."
    record["alert_message_id"] = alert(message)
    record["degraded_alert_day"] = day
    persist()
    return [{"unit": unit, "action": "degraded_alert"}]


def alert_source_lag(unit, record, day, alert, persist):
    if record.get('source_lag_alert_day') == day:
        return []
    record['alert_message_id'] = alert(f'Knowledge source consolidation is stale: {unit} has an eligible source revision pending for more than 26 hours. Successful publication does not mean ingestion is current.')
    record['source_lag_alert_day'] = day
    persist()
    return [{'unit': unit, 'action': 'source_lag_alert'}]


def publication_status(root, unit):
    scope = {"knowledge": "timeless", "whatsapp": "whatsapp", "engineering": "engineering"}[unit.split("-", 1)[0]]
    path = root / "data/knowledge-publication" / scope / "status.json"
    return json.loads(path.read_text()) if path.exists() else {}


def recover_sync(unit, record, day, alert, persist, retry):
    events = []
    if record.get("retry_day") != day:
        record["retry_day"] = day
        persist()
        try:
            retry(unit)
        except Exception:
            record["retry_failed"] = True
        events.append({"unit": unit, "action": "retry"})
    if record.get("alert_day") != day:
        record["alert_message_id"] = alert(f"Knowledge publishing needs attention: {unit} failed or has no successful run within 36 hours. One bounded retry was requested; checkpoints are preserved.")
        record["alert_day"] = day
        persist()
        events.append({"unit": unit, "action": "alert"})
    return events


def main():
    root = Path(__file__).resolve().parent.parent
    configure(root)
    path = root / "data/report-watchdog/state.json"
    state = json.loads(path.read_text()) if path.exists() else {"started_at": dt.datetime.now(dt.timezone.utc).timestamp(), "runs": {}}

    def retry(series):
        save(path, state)
        subprocess.run([str(root / "node_modules/.bin/tsx"), str(root / "src/cli/client.ts"),
                        "tasks", "run", "--id", series, "--group", GROUP],
                       cwd=root, check=True, capture_output=True, timeout=20)

    now = dt.datetime.now(dt.timezone.utc).timestamp()
    alert, persist = lambda text: telegram_alert(root, text), lambda: save(path, state)
    units = ["knowledge-wiki-sync.service", "whatsapp-wiki-sync.service"]
    if (root / "data/knowledge-publication/engineering").exists():
        units.append("engineering-wiki-sync.service")
    events = inspect_knowledge_sync(state, now, alert, persist, publication=lambda unit: publication_status(root, unit), units=units)
    events += inspect(root, state, now, retry, alert, persist)
    save(path, state)
    print(json.dumps({"ok": True, "events": events}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"ok": False, "error": type(error).__name__}))
        raise SystemExit(1)
