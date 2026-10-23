"""Keep ancestry checks on the reader and uploads on the restricted writer."""

import sys
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sync_knowledge_wiki as subject


class SyncCredentialsTest(unittest.TestCase):
    def test_corrupt_state_never_becomes_an_empty_new_upload_inventory(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "state.json"
            self.assertEqual(subject.load_state(path), {})
            for invalid in ["[]", "{broken", '{"page.md": 12}']:
                path.write_text(invalid)
                with self.assertRaises(ValueError):
                    subject.load_state(path)

    def test_unreadable_state_does_not_reset_existing_file_ids(self):
        with patch.object(Path, "read_text", side_effect=PermissionError("unreadable state")):
            with self.assertRaises(PermissionError):
                subject.load_state(Path("state.json"))

    def test_reader_validates_ancestry_without_replacing_writer(self):
        reader, writer = MagicMock(), MagicMock()
        writer.files().create.return_value.execute.return_value = {"id": "created_page_123"}
        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(sys, "argv", ["sync", "--source", root, "--drive-folder", "target_folder_123"]),
            patch.object(subject, "service", side_effect=lambda mode, authorize: reader if mode == "reader" else writer),
            patch.object(subject, "writer_parent", return_value="target_folder_123") as validate,
        ):
            (Path(root) / "page.md").write_text("# Source-grounded knowledge\n")
            subject.main()
        validate.assert_called_once_with(reader, "target_folder_123")
        reader.files.assert_not_called()
        writer.files().create.assert_called_once()

    def test_later_upload_failure_preserves_successful_file_id(self):
        import json
        writer = MagicMock()
        writer.files().create.return_value.execute.side_effect = [{"id": "first_page_123"}, RuntimeError("upload failed")]
        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(sys, "argv", ["sync", "--source", root, "--drive-folder", "target_folder_123"]),
            patch.object(subject, "service", return_value=writer),
            patch.object(subject, "writer_parent", return_value="target_folder_123"),
        ):
            for name in ["a.md", "b.md"]:
                (Path(root) / name).write_text("# Evidence\n")
            with self.assertRaisesRegex(RuntimeError, "upload failed"):
                subject.main()
            self.assertEqual(json.loads((Path(root) / ".drive-sync.json").read_text()), {"a.md": "first_page_123"})

    def test_only_changed_content_or_placement_is_uploaded(self):
        digest = hashlib.md5(b"# Evidence\n").hexdigest()
        for remote_digest, parents, upload in [(digest, ["target_folder_123"], False),
                                                ("different", ["target_folder_123"], True),
                                                (digest, ["wrong_folder_123"], True)]:
            with self.subTest(digest=remote_digest, parents=parents), tempfile.TemporaryDirectory() as root:
                writer = MagicMock()
                writer.files().get.return_value.execute.return_value = {"parents": parents, "md5Checksum": remote_digest}
                (Path(root) / "page.md").write_text("# Evidence\n")
                state = Path(root) / ".drive-sync.json"
                state.write_text(json.dumps({"page.md": "existing_page_123"}))
                with patch.object(sys, "argv", ["sync", "--source", root, "--drive-folder", "target_folder_123"]), \
                     patch.object(subject, "service", return_value=writer), \
                     patch.object(subject, "writer_parent", return_value="target_folder_123"):
                    subject.main()
                self.assertEqual(writer.files().update.called, upload)
                writer.files().create.assert_not_called()
                self.assertEqual(json.loads(state.read_text()), {"page.md": "existing_page_123"})


if __name__ == "__main__":
    unittest.main()
