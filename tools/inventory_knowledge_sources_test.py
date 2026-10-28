import importlib.util
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import unittest

with patch.dict("sys.modules", {"gdrive_assistant": MagicMock()}):
    spec = importlib.util.spec_from_file_location(
        "inventory", Path(__file__).with_name("inventory_knowledge_sources.py")
    )
    subject = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(subject)


class InventoryTests(unittest.TestCase):
    def test_eligibility_excludes_transcripts_and_whatsapp_by_path(self):
        for path, expected in [
            ("/meeting/AI Notes", True),
            ("/transcripts/note", False),
            ("/WhatsApp/note", False),
            ("/recording/note", False),
        ]:
            self.assertEqual(
                subject.eligible(
                    {"mimeType": "application/vnd.google-apps.document", "path": path}
                ),
                expected,
            )

    def test_unprocessed_source_is_not_a_successful_no_change_pass(self):
        f = {
            "id": "source",
            "mimeType": "text/plain",
            "path": "/AI Notes",
            "modifiedTime": "2026-10-27T12:00:00Z",
        }
        result = subject.report(
            [f], 1, {"source": {"modifiedTime": "2026-10-26T12:00:00Z"}}
        )
        self.assertEqual(result["pending_sources"], 1)
        self.assertIn("not meeting dates", subject.coverage_page("folder", result))

    def test_matching_revision_still_needs_legacy_semantic_review(self):
        f = {
            "id": "source",
            "mimeType": "text/plain",
            "path": "/AI Notes",
            "modifiedTime": "revision",
        }
        result = subject.report([f], 1, {"source": {"modifiedTime": "revision"}})
        self.assertEqual(result["pending"][0]["pending_reason"], "legacy_consolidation")
        self.assertEqual(
            subject.report(
                [f],
                1,
                {"source": {"modifiedTime": "revision", "consolidation_version": 2}},
            )["pending_sources"],
            0,
        )

    def test_queue_age_is_not_the_age_of_a_historical_source(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'state.json'
            result={'checked_at':'2026-10-28T12:00:00Z','pending':[{'id':'source','modifiedTime':'2026-09-01T00:00:00Z'}]}
            subject.stamp_pending(result,state)
            self.assertEqual(result['pending'][0]['pending_since'],result['checked_at'])
            state.write_text(json.dumps(result))
            later={**result,'checked_at':'2026-10-29T12:00:00Z','pending':[{'id':'source','modifiedTime':'2026-09-01T00:00:00Z'}]}
            subject.stamp_pending(later,state)
            self.assertEqual(later['pending'][0]['pending_since'],'2026-10-28T12:00:00Z')
            later['pending'][0]['modifiedTime']='2026-10-29T11:00:00Z'
            subject.stamp_pending(later,state)
            self.assertEqual(later['pending'][0]['pending_since'],later['checked_at'])

    def test_recursive_listing_follows_empty_provider_pages_and_continuations(self):
        api = MagicMock()
        seen = []

        def execute():
            requests = seen[:]
            seen.clear()
            for token, callback in requests:
                response = (
                    {"nextPageToken": "next", "files": []}
                    if token is None
                    else {
                        "files": [
                            {
                                "id": "note",
                                "name": "AI Notes",
                                "mimeType": "text/plain",
                                "modifiedTime": "date",
                            }
                        ]
                    }
                )
                callback("request", response, None)

        batch = MagicMock()
        batch.execute.side_effect = execute
        api.new_batch_http_request.return_value = batch
        api.files().list.side_effect = lambda **kw: kw["pageToken"]
        batch.add.side_effect = lambda request, callback: seen.append(
            (request, callback)
        )
        files, folders = subject.inventory(api, "approved_root")
        self.assertEqual((len(files), folders), (1, 1))
        self.assertEqual(api.files().list.call_count, 2)

    def test_provider_error_cannot_publish_complete_inventory(self):
        api = MagicMock()
        callbacks = []
        batch = MagicMock()
        api.new_batch_http_request.return_value = batch
        batch.add.side_effect = lambda request, callback: callbacks.append(callback)
        batch.execute.side_effect = lambda: callbacks[0](
            "r", None, RuntimeError("unavailable")
        )
        with self.assertRaisesRegex(RuntimeError, "Incomplete"):
            subject.inventory(api, "approved_root")

    def test_source_versions_are_immutable_and_bound_to_observed_revision(self):
        api = MagicMock()
        api.files().export_media.return_value.execute.return_value = b"original source"
        api.files().get.return_value.execute.return_value = {
            "modifiedTime": "revision1"
        }
        item = {
            "id": "source",
            "mimeType": "application/vnd.google-apps.document",
            "modifiedTime": "revision1",
        }
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subject.cache_source(api, item, root)
            first = next(root.rglob("*.json"))
            before = first.read_bytes()
            api.files().export_media.return_value.execute.return_value = b"new source"
            api.files().get.return_value.execute.return_value = {
                "modifiedTime": "revision2"
            }
            subject.cache_source(api, {**item, "modifiedTime": "revision2"}, root)
            self.assertEqual(first.read_bytes(), before)
            self.assertEqual(len(list(root.rglob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
