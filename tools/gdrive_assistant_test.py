"""Regression tests for Google OAuth recovery behavior."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import gdrive_assistant as subject
from google.auth.exceptions import RefreshError


class AtomicTokenTest(unittest.TestCase):
    def test_readers_keep_the_complete_previous_token_until_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "reader-token.json"
            destination.write_text("old grant")
            replace = Path.replace
            def publish(temporary, target):
                self.assertEqual(destination.read_text(), "old grant")
                self.assertEqual(temporary.read_text(), "new grant")
                self.assertEqual(temporary.stat().st_mode & 0o777, 0o600)
                return replace(temporary, target)
            with patch.object(Path, "replace", publish):
                subject.save_token(destination, "new grant")
            self.assertEqual(destination.read_text(), "new grant")
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_failed_publication_preserves_the_previous_token(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "reader-token.json"
            destination.write_text("old grant")
            with patch.object(Path, "replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    subject.save_token(destination, "new grant")
            self.assertEqual(destination.read_text(), "old grant")
            self.assertEqual(list(Path(directory).iterdir()), [destination])


class OAuthRecoveryTest(unittest.TestCase):
    def test_auth_replaces_a_revoked_token_with_browser_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "reader-token.json"
            token_path.write_text("{}")
            revoked = MagicMock(expired=True, refresh_token="present")
            revoked.refresh.side_effect = RefreshError("invalid_grant")
            authorized = MagicMock(valid=True)
            authorized.to_json.return_value = "{}"
            flow = MagicMock()
            flow.run_local_server.return_value = authorized

            with (
                patch.dict(subject.TOKENS, {"reader": token_path}),
                patch.object(subject.Credentials, "from_authorized_user_file", return_value=revoked),
                patch.object(subject.InstalledAppFlow, "from_client_secrets_file", return_value=flow),
                patch.object(subject, "build"),
            ):
                subject.service("reader", authorize=True)

            flow.run_local_server.assert_called_once_with(
                host="127.0.0.1", port=8080, open_browser=False,
                access_type="offline", prompt="consent",
            )
            self.assertTrue(token_path.exists())

    def test_explicit_auth_replaces_even_a_valid_testing_grant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "reader-token.json"
            token_path.write_text("old grant")
            flow = MagicMock()
            flow.run_local_server.return_value.to_json.return_value = "fresh grant"
            with (
                patch.dict(subject.TOKENS, {"reader": token_path}),
                patch.object(subject.Credentials, "from_authorized_user_file") as load,
                patch.object(subject.InstalledAppFlow, "from_client_secrets_file", return_value=flow),
                patch.object(subject, "build"),
            ):
                subject.service("reader", authorize=True)
            load.assert_not_called()
            self.assertEqual(token_path.read_text(), "fresh grant")

    def test_rejected_background_refresh_preserves_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "reader-token.json"
            token_path.write_text("old grant")
            creds = MagicMock(expired=True, refresh_token="present")
            creds.refresh.side_effect = RefreshError("invalid_grant")
            with (
                patch.dict(subject.TOKENS, {"reader": token_path}),
                patch.object(subject.Credentials, "from_authorized_user_file", return_value=creds),
                patch.object(subject.InstalledAppFlow, "from_client_secrets_file") as flow,
                self.assertRaisesRegex(RuntimeError, "In production"),
            ):
                subject.service("reader", authorize=False)
            flow.assert_not_called()
            self.assertEqual(token_path.read_text(), "old grant")


class VideoDownloadTest(unittest.TestCase):
    def test_byte_limit_is_enforced_before_writing(self):
        import io
        output = io.BytesIO()
        stream = subject.BoundedVideoFile(output)
        with patch.object(subject, "MAX_VIDEO_BYTES", 3):
            stream.write(b"abc")
            with self.assertRaisesRegex(RuntimeError, "exceeds"):
                stream.write(b"d")
        self.assertEqual(output.getvalue(), b"abc")

    def test_download_and_cleanup_on_changed_metadata(self):
        meta = {"id": "selected_video_123", "name": "../../owner.mp4", "mimeType": "video/mp4", "size": "12", "version": "1"}
        api = MagicMock()
        download = MagicMock()
        def chunk(*args, **kwargs):
            stream.write(b"0000ftyp0000")
            return None, True
        def downloader(output, request, chunksize):
            nonlocal stream
            stream = output
            download.next_chunk.side_effect = chunk
            return download
        stream = None
        with tempfile.TemporaryDirectory() as directory, patch.object(subject, "service", return_value=api), patch.object(subject, "MediaIoBaseDownload", side_effect=downloader):
            api.files().get().execute.side_effect = [meta, meta]
            result = subject.download_video("selected_video_123", directory)
            self.assertEqual(Path(result["path"]).name, "selected-video.mp4")
            self.assertEqual(result["version"], "1")
            Path(result["path"]).unlink()
            api.files().get().execute.side_effect = [meta, {**meta, "version": "2"}]
            with self.assertRaisesRegex(RuntimeError, "changed"):
                subject.download_video("selected_video_123", directory)
            self.assertFalse(list(Path(directory).iterdir()))

    def test_invalid_id_and_unsupported_or_oversized_metadata(self):
        with patch.object(subject, "service") as service:
            with self.assertRaisesRegex(RuntimeError, "invalid"):
                subject.download_video("../invalid", "/tmp")
            service.assert_not_called()
            for mime, size in [("application/vnd.google-apps.shortcut", "10"), ("video/mp4", str(subject.MAX_VIDEO_BYTES + 1)), ("video/mp4", "0")]:
                service.return_value.files().get().execute.return_value = {"mimeType": mime, "size": size}
                with self.assertRaises(RuntimeError):
                    subject.download_video("selected_video_123", "/tmp")



class TextReadCompletenessTest(unittest.TestCase):
    def test_raw_cli_fails_before_output_when_text_is_oversized(self):
        api = MagicMock()
        api.files().get.return_value.execute.return_value = {'name': 'large.txt', 'mimeType': 'text/plain'}
        api.files().get_media.return_value.execute.return_value = b'x' * 1_000_001
        with patch.object(subject, 'service', return_value=api), patch.object(subject.sys, 'stdout') as output:
            with self.assertRaisesRegex(RuntimeError, 'offset/version continuation'):
                subject.read('large-file')
            output.buffer.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
