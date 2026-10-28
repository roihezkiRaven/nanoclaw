"""Check source-day attribution without Drive or credentials."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

with patch.dict("sys.modules", {"gdrive_assistant": MagicMock()}):
    spec = importlib.util.spec_from_file_location(
        "audit", Path(__file__).with_name("audit_whatsapp_wiki.py")
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def test_days_follow_message_utc_time_not_filename_or_local_date(self):
        text = json.dumps(
            {"groupJid": "123456789@g.us", "timestamp": "2026-10-28T00:30:00+03:00"}
        )
        self.assertEqual(list(audit.records(text)), [("123456789@g.us", "2026-10-27")])

    def test_legacy_literal_newline_is_lossless_but_bad_records_fail(self):
        text = '{"groupJid":"123456789@g.us","timestamp":"2026-10-28T00:00:00Z","text":"first\nsecond"}'
        self.assertEqual(len(list(audit.records(text))), 1)
        with self.assertRaises(ValueError):
            list(audit.records(text + "broken"))
        with self.assertRaises(ValueError):
            list(audit.records(text.replace("00:00:00Z", "00:00:00")))

    def test_missing_day_source_and_duplicate_day_are_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            expected = {("123456789@g.us", "2026-10-28"): {"source-one", "source-two"}}
            self.assertTrue(audit.coverage_errors(root, expected))
            page = root / "whatsapp/group/2026-10-28.md"
            page.parent.mkdir(parents=True)
            page.write_text(
                '---\ntype: digest\ngroup_jid: "123456789@g.us"\nsources: [source-one]\n---\nSummary'
            )
            self.assertTrue(audit.coverage_errors(root, expected))
            page.write_text(
                page.read_text().replace("[source-one]", "[source-one, source-two]")
            )
            self.assertFalse(audit.coverage_errors(root, expected))
            duplicate = root / "whatsapp/other/2026-10-28.md"
            duplicate.parent.mkdir()
            duplicate.write_text(page.read_text())
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                audit.digest_pages(root)


if __name__ == "__main__":
    unittest.main()
