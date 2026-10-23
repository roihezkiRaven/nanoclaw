import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("watchdog", Path(__file__).with_name("report-watchdog.py"))
watchdog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watchdog)


class DeliveryWatchdogTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        config = self.root / "config/report-watchdog.json"
        config.parent.mkdir()
        config.write_text(json.dumps({"group_id": "ag-test-owner", "reports": ["whatsapp-daily-digest-test"],
                                      "platform_destinations": {"telegram": "telegram:123456789", "slack": "slack:C0123456789"}}))
        watchdog.configure(self.root)
        folder = self.root / "data/v2-sessions" / watchdog.GROUP / "session"
        folder.mkdir(parents=True)
        self.inbound = sqlite3.connect(folder / "inbound.db")
        self.outbound = sqlite3.connect(folder / "outbound.db")
        self.addCleanup(self.inbound.close)
        self.addCleanup(self.outbound.close)
        self.inbound.executescript("CREATE TABLE messages_in(id,series_id,process_after,status,kind); CREATE TABLE delivered(message_out_id,status,platform_message_id);")
        self.outbound.executescript("CREATE TABLE messages_out(id,kind,channel_type,platform_id,timestamp,content,in_reply_to);")
        self.inbound.execute("INSERT INTO messages_in VALUES ('run','whatsapp-daily-digest-test','2026-10-04T18:00:00Z','failed','task')")
        self.inbound.commit()
        with sqlite3.connect(self.root / "data/v2.db") as db:
            db.execute("CREATE TABLE sessions(id,agent_group_id,thread_id)")
            db.execute("INSERT INTO sessions VALUES ('session',?,'system:tasks:whatsapp-daily-digest-test')", (watchdog.GROUP,))
        self.start = watchdog.timestamp("2026-10-04T18:00:00Z")
        self.state = {"started_at": self.start, "runs": {}}
        self.retries, self.alerts = [], []

    def inspect(self, seconds=3600):
        return watchdog.inspect(self.root, self.state, self.start + seconds, self.retries.append,
                                lambda text: self.alerts.append(text) or 123)

    def receipt(self, channel, platform_message_id="confirmed", text="Useful brief", reply_to="run"):
        self.outbound.execute("INSERT INTO messages_out VALUES (?,?,?,?,?,?,?)", (channel, "chat", channel,
            watchdog.DESTINATIONS[channel], "2026-10-04T18:01:00Z", json.dumps({"text": text}), reply_to))
        self.inbound.execute("INSERT INTO delivered VALUES (?,'delivered',?)", (channel, platform_message_id))
        self.outbound.commit()
        self.inbound.commit()

    def test_one_retry_then_one_alert_and_no_repeat(self):
        self.inspect()
        self.assertEqual(len(self.retries), 1)
        self.inspect(4000)
        self.assertEqual(len(self.retries), 1)
        self.inspect(5500)
        self.inspect(6000)
        self.assertEqual(len(self.alerts), 1)

    def test_failed_sync_retries_once_and_alerts_without_using_the_model(self):
        properties = lambda unit: {"Result": "exit-code", "ActiveState": "failed", "ExecMainExitTimestamp": ""}
        for _ in range(2):
            watchdog.inspect_knowledge_sync(self.state, self.start, self.alerts.append, lambda: None,
                                             properties, self.retries.append)
        self.assertEqual(len(self.retries), 2)
        self.assertEqual(len(self.alerts), 2)

    def test_healthy_or_running_sync_needs_no_recovery(self):
        for status in ["inactive", "activating"]:
            properties = lambda unit: {"Result": "success", "ActiveState": status, "ExecMainExitTimestamp": "Sun 2026-10-04 18:00:00 UTC"}
            watchdog.inspect_knowledge_sync(self.state, self.start + 3600, self.alerts.append, lambda: None,
                                             properties, self.retries.append)
        self.assertFalse(self.retries + self.alerts)

    def test_stale_success_is_not_mistaken_for_a_fresh_sync(self):
        properties = lambda unit: {"Result": "success", "ActiveState": "inactive", "ExecMainExitTimestamp": "Sun 2026-10-04 18:00:00 UTC"}
        watchdog.inspect_knowledge_sync(self.state, self.start + 37 * 3600, self.alerts.append, lambda: None,
                                         properties, self.retries.append)
        self.assertEqual(len(self.alerts), 2)

    def test_invalid_alert_configuration_fails_closed(self):
        path = self.root / "config/report-watchdog.json"
        settings = json.loads(path.read_text())
        settings["platform_destinations"]["telegram"] = "unconfigured"
        path.write_text(json.dumps(settings))
        with self.assertRaises(ValueError):
            watchdog.configure(self.root)

    def test_null_receipt_and_error_notice_do_not_prove_delivery(self):
        self.receipt("telegram", None)
        self.receipt("slack", "id", "Error: Authentication expired")
        self.inspect()
        self.assertEqual(len(self.retries), 1)

    def test_empty_receipt_id_does_not_prove_delivery(self):
        self.receipt("telegram", "")
        self.receipt("slack", "  ")
        self.inspect()
        self.assertEqual(len(self.retries), 1)

    def test_partial_delivery_alerts_without_duplicate_report(self):
        self.receipt("telegram")
        self.inspect()
        self.assertFalse(self.retries)
        self.assertIn("slack", self.alerts[0])

    def test_confirmed_delivery_needs_no_retry_or_alert(self):
        self.receipt("telegram")
        self.receipt("slack")
        self.inspect()
        self.assertFalse(self.retries + self.alerts)

    def test_unrelated_chat_cannot_hide_a_missed_report(self):
        self.receipt("telegram", reply_to="unrelated-system-response")
        self.receipt("slack", reply_to="unrelated-system-response")
        self.inspect()
        self.assertEqual(len(self.retries), 1)

    def test_newer_run_does_not_hide_an_older_missing_report_day(self):
        self.inbound.execute("INSERT INTO messages_in VALUES ('older','whatsapp-daily-digest-test','2026-10-03T18:00:00Z','failed','task')")
        self.inbound.commit()
        self.state["started_at"] -= 86400
        self.receipt("telegram")
        self.receipt("slack")
        self.inspect()
        self.assertEqual(len(self.alerts), 1)
        self.assertIn("2026-10-03", self.alerts[0])
        self.assertFalse(self.retries)

    def test_confirmed_alert_is_persisted_immediately(self):
        self.receipt("telegram")
        persisted = []
        watchdog.inspect(self.root, self.state, self.start + 3600, self.retries.append,
                         lambda text: 123, lambda: persisted.append(json.loads(json.dumps(self.state))))
        self.assertEqual(next(iter(persisted[-1]["runs"].values()))["alert_message_id"], 123)

    def test_paused_task_and_intentional_single_destination(self):
        self.inbound.execute("UPDATE messages_in SET status='paused'")
        self.inbound.commit()
        self.inspect()
        self.assertFalse(self.retries + self.alerts)
        self.inbound.execute("UPDATE messages_in SET status='completed'")
        self.inbound.commit()
        self.receipt("telegram")
        path = self.root / "groups/personal-assistant/work/report-delivery.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"destinations": {"whatsapp-daily-digest-test": ["telegram"]}}))
        self.inspect()
        self.assertFalse(self.retries + self.alerts)


if __name__ == "__main__":
    unittest.main()
