"""Regression tests for Google OAuth recovery behavior."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import gdrive_assistant as subject
from google.auth.exceptions import RefreshError


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

            flow.run_local_server.assert_called_once()
            self.assertTrue(token_path.exists())


if __name__ == "__main__":
    unittest.main()
